"""Issues router."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
import os
import uuid as _uuid

from fastapi import UploadFile, File

from app.config import settings
from app.models import Issue, IssueStatusHistory, Site, Courtyard, District, User, Photo
from app.schemas import IssueCreate, IssueUpdate, IssueOut, IssueListOut, UserOut, PhotoOut
from app.services.auth import get_current_user
from app.services.permissions import require_role, check_own_or_role, in_district_scope
from app.services.audit import log_action

router = APIRouter()


def _issue_to_out(i: Issue) -> IssueOut:
    """Преобразовать модель Issue в схему IssueOut с обогащёнными данными."""
    site_name = None
    district_name = None
    if i.site_ref:
        site_name = i.site_ref.courtyard.name if i.site_ref.courtyard else None
        if i.site_ref.courtyard and i.site_ref.courtyard.district:
            district_name = i.site_ref.courtyard.district.name

    def _photo_out(p):
        return PhotoOut(
            id=p.id, target_type=p.target_type,
            inspection_id=p.inspection_id, issue_id=p.issue_id,
            url=f"/uploads/{p.storage_path}",
            thumbnail_url=f"/uploads/{p.thumbnail_path}" if p.thumbnail_path else None,
            gps_lat=p.gps_lat, gps_lon=p.gps_lon,
            taken_at=p.taken_at, created_at=p.created_at,
        )

    # фото самого нарушения (документируют, что было найдено) и отдельно — фото исправления
    photos = [_photo_out(p) for p in i.photos]
    fix_photos = [_photo_out(p) for p in i.fix_photos]

    return IssueOut(
        id=i.id,
        title=i.title,
        description=i.description,
        criticality=i.criticality,
        status=i.status,
        site_id=i.site_id,
        inspection_id=i.inspection_id,
        assigned_to=i.assigned_to,
        assigned_user=UserOut.model_validate(i.assigned_user) if i.assigned_user else None,
        due_date=i.due_date,
        created_by=i.created_by,
        creator=UserOut.model_validate(i.creator_ref) if hasattr(i, 'creator_ref') and i.creator_ref else None,
        site_name=site_name,
        district_name=district_name,
        fix_comment=i.fix_comment if hasattr(i, 'fix_comment') else None,
        reviewer_comment=i.reviewer_comment if hasattr(i, 'reviewer_comment') else None,
        photos=photos,
        fix_photos=fix_photos,
        created_at=i.created_at,
        updated_at=i.updated_at,
    )


@router.post("/", response_model=IssueOut)
async def create_issue(
    data: IssueCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Замечание можно завести только на СВОЁМ обходе (инспектор) либо
    # проверяющему/админу — иначе кто угодно, зная UUID чужого обхода,
    # мог бы подложить туда фиктивное замечание.
    from app.models import Inspection
    insp = (await db.execute(
        select(Inspection).where(Inspection.id == data.inspection_id)
    )).scalar_one_or_none()
    if not insp:
        raise HTTPException(404, "Обход не найден")
    check_own_or_role(current_user, insp.inspector_id, "reviewer", "admin")

    issue = Issue(
        inspection_id=data.inspection_id,
        site_id=insp.site_id,
        title=data.title,
        description=data.description,
        criticality=data.criticality,
        status="open",
        created_by=current_user.id,
    )

    db.add(issue)
    await db.commit()
    await db.refresh(issue)

    # перезагружаем с eager-load
    q = select(Issue).where(Issue.id == issue.id).options(
        selectinload(Issue.site_ref).selectinload(Site.courtyard).selectinload(Courtyard.district),
        selectinload(Issue.assigned_user),
        selectinload(Issue.creator_ref),
        selectinload(Issue.photos),
        selectinload(Issue.fix_photos),
    )
    issue = (await db.execute(q)).scalar_one()
    return _issue_to_out(issue)


@router.get("/", response_model=IssueListOut)
async def list_issues(
    site_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    criticality: Optional[str] = Query(None),
    district_id: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base = select(Issue).options(
        selectinload(Issue.site_ref).selectinload(Site.courtyard).selectinload(Courtyard.district),
        selectinload(Issue.assigned_user),
        selectinload(Issue.creator_ref),
        selectinload(Issue.photos),
        selectinload(Issue.fix_photos),
    ).order_by(Issue.created_at.desc())

    if site_id:
        base = base.where(Issue.site_id == site_id)
    if status:
        base = base.where(Issue.status == status)
    if criticality:
        base = base.where(Issue.criticality == criticality)
    if assigned_to:
        base = base.where(Issue.assigned_to == assigned_to)

    effective_district_id = district_id
    if current_user.role == "reviewer" and current_user.district_id is not None:
        effective_district_id = str(current_user.district_id)
    if current_user.role == "inspector":
        base = base.where(Issue.created_by == current_user.id)

    if effective_district_id:
        base = base.join(Site, Issue.site_id == Site.id).join(
            Courtyard, Site.courtyard_id == Courtyard.id
        ).where(Courtyard.district_id == effective_district_id)

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    rows = (await db.execute(base.offset(offset).limit(page_size))).scalars().all()

    return IssueListOut(
        total=total,
        items=[_issue_to_out(r) for r in rows],
    )


@router.get("/{issue_id}", response_model=IssueOut)
async def get_issue(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Issue).where(Issue.id == issue_id).options(
        selectinload(Issue.site_ref).selectinload(Site.courtyard).selectinload(Courtyard.district),
        selectinload(Issue.assigned_user),
        selectinload(Issue.creator_ref),
        selectinload(Issue.photos),
        selectinload(Issue.fix_photos),
    )
    issue = (await db.execute(q)).scalar_one_or_none()
    if not issue:
        raise HTTPException(404, "Замечание не найдено")

    if current_user.role == "inspector":
        check_own_or_role(current_user, issue.created_by, "reviewer", "admin")
    elif current_user.role == "reviewer":
        district_id = issue.site_ref.courtyard.district_id if issue.site_ref and issue.site_ref.courtyard else None
        if not in_district_scope(current_user, district_id):
            raise HTTPException(403, "Замечание вне вашего района")

    return _issue_to_out(issue)


@router.put("/{issue_id}", response_model=IssueOut)
async def update_issue(
    issue_id: str,
    data: IssueUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("reviewer", "admin")),
):
    issue = (await db.execute(
        select(Issue).where(Issue.id == issue_id).options(
            selectinload(Issue.site_ref).selectinload(Site.courtyard).selectinload(Courtyard.district),
            selectinload(Issue.assigned_user),
            selectinload(Issue.creator_ref),
        )
    )).scalar_one_or_none()
    if not issue:
        raise HTTPException(404, "Замечание не найдено")

    if current_user.role == "reviewer":
        district_id = issue.site_ref.courtyard.district_id if issue.site_ref and issue.site_ref.courtyard else None
        if not in_district_scope(current_user, district_id):
            raise HTTPException(403, "Замечание вне вашего района")

    old_status = issue.status

    if data.status and data.status != issue.status:
        # Цепочка инспектор→проверяющий→админ: проверяющий доводит
        # замечание до fixed (с фото устранения), а финальное решение —
        # принять (closed) или вернуть на доработку (revision_needed) —
        # только у админа, и только из статуса fixed (нельзя закрыть
        # замечание, которое проверяющий ещё не довёл до этого статуса).
        if data.status in ('closed', 'revision_needed'):
            if current_user.role != 'admin':
                raise HTTPException(403, "Принять или вернуть на доработку может только админ")
            if issue.status != 'fixed':
                raise HTTPException(400, "Замечание должно быть в статусе «Исправлено» с фото, прежде чем принять решение")
            if data.status == 'revision_needed':
                if not data.reviewer_comment:
                    raise HTTPException(400, "Укажите комментарий — что нужно доработать")
                issue.reviewer_comment = data.reviewer_comment

        if data.status == "fixed":
            # Именно фото ИСПРАВЛЕНИЯ (target_type='issue_fix'), а не любое
            # фото на issue_id — с появлением фото самого нарушения
            # (POST /issues/{id}/photos, target_type='issue') подсчёт без
            # фильтра по типу засчитывал фото нарушения как доказательство
            # исправления, и статус можно было выставить fixed вообще без
            # фото результата
            photo_count = (await db.execute(
                select(func.count()).select_from(Photo).where(
                    Photo.issue_id == issue_id, Photo.target_type == "issue_fix",
                )
            )).scalar_one()
            if photo_count == 0:
                raise HTTPException(400, "Нужно приложить хотя бы одно фото исправления")
            issue.fixed_at = datetime.now(timezone.utc)

        issue.status = data.status

        # запись в историю
        db.add(IssueStatusHistory(
            issue_id=issue_id,
            old_status=old_status,
            new_status=data.status,
            changed_by=current_user.id,
            comment=data.comment,
        ))

    # model_fields_set, не "is not None" — иначе явный null (снять
    # назначение через "Не назначен" в форме) неотличим от "поле не
    # прислали", и снять уже назначенного исполнителя невозможно (тот же
    # класс бага, что уже был исправлен для UserRoleUpdate.district_id).
    if "assigned_to" in data.model_fields_set:
        issue.assigned_to = data.assigned_to
    if data.due_date is not None:
        issue.due_date = data.due_date
    if data.fix_comment is not None:
        issue.fix_comment = data.fix_comment
    if data.reviewer_comment is not None:
        issue.reviewer_comment = data.reviewer_comment

    issue.updated_at = datetime.now(timezone.utc)
    await log_action(db, str(current_user.id), "issue_update", "issue", issue_id, {
        "status": data.status, "assigned_to": str(data.assigned_to) if data.assigned_to else None,
        "reviewer_comment": data.reviewer_comment,
    })
    await db.commit()

    # перезагружаем
    q = select(Issue).where(Issue.id == issue_id).options(
        selectinload(Issue.site_ref).selectinload(Site.courtyard).selectinload(Courtyard.district),
        selectinload(Issue.assigned_user),
        selectinload(Issue.creator_ref),
        selectinload(Issue.photos),
        selectinload(Issue.fix_photos),
    )
    issue = (await db.execute(q)).scalar_one()
    return _issue_to_out(issue)


UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "uploads")


@router.post("/{issue_id}/photos", response_model=PhotoOut)
async def upload_issue_photo(
    issue_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Загрузить фото самого нарушения (не путать с фото исправления) —
    чтобы каждое замечание документировалось отдельно, а не тонуло в общих
    фото обхода."""
    issue = (await db.execute(
        select(Issue).where(Issue.id == issue_id).options(
            selectinload(Issue.site_ref).selectinload(Site.courtyard),
        )
    )).scalar_one_or_none()
    if not issue:
        raise HTTPException(404, "Замечание не найдено")

    if current_user.role == "inspector":
        check_own_or_role(current_user, issue.created_by, "reviewer", "admin")
    elif current_user.role == "reviewer":
        district_id = issue.site_ref.courtyard.district_id if issue.site_ref and issue.site_ref.courtyard else None
        if not in_district_scope(current_user, district_id):
            raise HTTPException(403, "Замечание вне вашего района")

    ext = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "jpg"
    safe_ext = ext.lower()[:5]
    filename = f"{_uuid.uuid4()}.{safe_ext}"
    rel_path = os.path.join("issues", filename)
    abs_path = os.path.join(UPLOAD_DIR, rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    max_bytes = settings.MAX_PHOTO_SIZE_MB * 1024 * 1024
    size = 0
    with open(abs_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                f.close()
                os.remove(abs_path)
                raise HTTPException(413, f"Файл больше {settings.MAX_PHOTO_SIZE_MB} МБ")
            f.write(chunk)

    photo = Photo(
        target_type="issue",
        issue_id=issue.id,
        storage_path=rel_path,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)

    return PhotoOut(
        id=photo.id, target_type=photo.target_type,
        inspection_id=photo.inspection_id, issue_id=photo.issue_id,
        url=f"/uploads/{photo.storage_path}",
        thumbnail_url=None, gps_lat=None, gps_lon=None,
        taken_at=None, created_at=photo.created_at,
    )


@router.post("/{issue_id}/fix-photos", response_model=PhotoOut)
async def upload_fix_photo(
    issue_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("reviewer", "admin")),
):
    """Загрузить фото исправления для замечания."""
    issue = (await db.execute(
        select(Issue).where(Issue.id == issue_id).options(
            selectinload(Issue.site_ref).selectinload(Site.courtyard),
        )
    )).scalar_one_or_none()
    if not issue:
        raise HTTPException(404, "Замечание не найдено")

    if current_user.role == "reviewer":
        district_id = issue.site_ref.courtyard.district_id if issue.site_ref and issue.site_ref.courtyard else None
        if not in_district_scope(current_user, district_id):
            raise HTTPException(403, "Замечание вне вашего района")

    ext = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "jpg"
    safe_ext = ext.lower()[:5]
    filename = f"{_uuid.uuid4()}.{safe_ext}"
    rel_path = os.path.join("issues", filename)
    abs_path = os.path.join(UPLOAD_DIR, rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    max_bytes = settings.MAX_PHOTO_SIZE_MB * 1024 * 1024
    size = 0
    with open(abs_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                f.close()
                os.remove(abs_path)
                raise HTTPException(413, f"Файл больше {settings.MAX_PHOTO_SIZE_MB} МБ")
            f.write(chunk)

    photo = Photo(
        target_type="issue_fix",
        issue_id=issue.id,
        storage_path=rel_path,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)

    return PhotoOut(
        id=photo.id, target_type=photo.target_type,
        inspection_id=photo.inspection_id, issue_id=photo.issue_id,
        url=f"/uploads/{photo.storage_path}",
        thumbnail_url=None, gps_lat=None, gps_lon=None,
        taken_at=None, created_at=photo.created_at,
    )
