"""Inspections router."""
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid as _uuid
import os

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.services.permissions import check_own_or_role, in_district_scope
from app.services.timezone import MSK
from app.models import (
    Inspection, Site, Courtyard, District, User,
    ChecklistAnswer, ChecklistItem, ChecklistTemplate, Photo, Issue,
)
from app.schemas import (
    InspectionCreate, InspectionUpdate, InspectionOut,
    InspectionListOut, ChecklistAnswerOut, SiteOut, UserOut,
    DistrictOut, CourtyardOut, PhotoOut,
    InspectionBulkAcceptRequest, InspectionBulkAcceptOut,
)
from app.services.auth import get_current_user
from app.services.audit import log_action

router = APIRouter()


@router.post("/", response_model=InspectionOut)
async def create_inspection(
    data: InspectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    site = (await db.execute(
        select(Site)
        .where(Site.id == data.site_id)
        .options(
            selectinload(Site.courtyard).selectinload(Courtyard.district),
        )
    )).scalar_one_or_none()
    if not site:
        raise HTTPException(404, "Площадка не найдена")

    # Продолжаем свой же незавершённый обход этой площадки вне зависимости
    # от того, в какой день он был начат — иначе обход, вернувшийся на
    # доработку (status снова 'in_progress') несколько дней назад, не
    # находится проверкой "за сегодня" ниже, и повторное "Начать обход"
    # тихо создаёт ещё один, осиротив исходный
    own_unfinished = (await db.execute(
        select(Inspection).where(
            Inspection.site_id == data.site_id,
            Inspection.inspector_id == current_user.id,
            Inspection.status.in_(("planned", "in_progress")),
        ).order_by(Inspection.created_at.desc())
    )).scalars().first()
    if own_unfinished:
        q = select(Inspection).where(Inspection.id == own_unfinished.id).options(
            selectinload(Inspection.site).selectinload(Site.courtyard).selectinload(Courtyard.district),
            selectinload(Inspection.inspector),
            selectinload(Inspection.answers),
            selectinload(Inspection.reviewed_by_user),
        )
        own_unfinished = (await db.execute(q)).scalar_one()
        return await _inspection_to_out(own_unfinished, db)

    # Одна проверка площадки в сутки НА ИНСПЕКТОРА — чтобы у одного
    # человека не копились случайные повторные "Начать обход" по той же
    # площадке в тот же день. Изначально лимит был глобальным (кто угодно
    # один раз в день), но на реальном использовании выяснилось, что
    # маршруты инспекторов пересекаются — второй инспектор, придя на уже
    # отмеченную коллегой сегодня площадку, получал 409 и не мог начать
    # СВОЙ обход вообще. Полночь берём московскую, а не UTC — иначе
    # "сутки" физически начинались в 03:00 по Москве (00:00 UTC), и
    # вчерашние обходы с 00:00 до 03:00 МСК ошибочно не засчитывались как
    # сегодняшние.
    # ENABLE_DAILY_INSPECTION_LIMIT=false в .env — аварийно отключить эту
    # проверку без редеплоя, если она где-то мешает реальной работе.
    if settings.ENABLE_DAILY_INSPECTION_LIMIT:
        today_start = datetime.now(MSK).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        existing_today = (await db.execute(
            select(Inspection).where(
                Inspection.site_id == data.site_id,
                Inspection.inspector_id == current_user.id,
                Inspection.created_at >= today_start,
            ).order_by(Inspection.created_at.desc())
        )).scalars().first()
        if existing_today:
            raise HTTPException(409, "Вы уже проверяли эту площадку сегодня — повторный обход в этот же день не нужен")

    # подбираем шаблон чек-листа по типу площадки
    tmpl = (await db.execute(
        select(ChecklistTemplate).where(
            ChecklistTemplate.site_type == site.type, ChecklistTemplate.is_active
        )
    )).scalar_one_or_none()

    inspection = Inspection(
        site_id=data.site_id,
        inspector_id=current_user.id,
        template_id=tmpl.id if tmpl else None,
        type=data.type,
        status="in_progress",
        started_at=datetime.now(timezone.utc),
    )
    db.add(inspection)
    await db.commit()

    # Перезагружаем с eager-load для _inspection_to_out
    q = select(Inspection).where(Inspection.id == inspection.id).options(
        selectinload(Inspection.site).selectinload(Site.courtyard).selectinload(Courtyard.district),
        selectinload(Inspection.inspector),
        selectinload(Inspection.answers),
        selectinload(Inspection.reviewed_by_user),
    )
    inspection = (await db.execute(q)).scalar_one()
    return await _inspection_to_out(inspection, db)


@router.get("/", response_model=InspectionListOut)
async def list_inspections(
    site_id: Optional[str] = Query(None),
    inspector_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    district_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base = select(Inspection).options(
        selectinload(Inspection.site).selectinload(Site.courtyard).selectinload(Courtyard.district),
        selectinload(Inspection.inspector),
        selectinload(Inspection.answers),
        selectinload(Inspection.reviewed_by_user),
    ).order_by(Inspection.created_at.desc())

    if site_id:
        base = base.where(Inspection.site_id == site_id)
    if status:
        base = base.where(Inspection.status == status)

    if current_user.role == "inspector":
        # инспектор видит только свои обходы, даже если передан чужой inspector_id
        base = base.where(Inspection.inspector_id == current_user.id)
    elif inspector_id:
        base = base.where(Inspection.inspector_id == inspector_id)

    # Проверяющий со своим районом всегда ограничен им; иначе (округ-wide
    # проверяющий или admin) — можно явно выбрать район через district_id
    effective_district_id = district_id
    if current_user.role == "reviewer" and current_user.district_id is not None:
        effective_district_id = str(current_user.district_id)

    if effective_district_id:
        base = base.join(Site, Inspection.site_id == Site.id).join(
            Courtyard, Site.courtyard_id == Courtyard.id
        ).where(Courtyard.district_id == effective_district_id)

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    q = base.offset(offset).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    # Пакетно вместо по 2 запроса на строку (см. комментарий в
    # _inspection_to_out) — иначе MapPage/MyInspectionsPage с page_size
    # 500-1000 превращаются в тысячи последовательных запросов.
    ids = [r.id for r in rows]
    issues_counts: dict = {}
    photos_by_inspection: dict = {}
    if ids:
        for insp_id, cnt in (await db.execute(
            select(Issue.inspection_id, func.count())
            .where(Issue.inspection_id.in_(ids))
            .group_by(Issue.inspection_id)
        )).all():
            issues_counts[insp_id] = cnt

        for p in (await db.execute(
            select(Photo).where(
                Photo.inspection_id.in_(ids),
                Photo.target_type.in_(["inspection", "checklist_answer"]),
            ).order_by(Photo.created_at.asc())
        )).scalars().all():
            photos_by_inspection.setdefault(p.inspection_id, []).append(p)

    items = [
        await _inspection_to_out(
            i, db,
            _issues_count=issues_counts.get(i.id, 0),
            _photos=photos_by_inspection.get(i.id, []),
        )
        for i in rows
    ]
    return InspectionListOut(total=total, items=items)


@router.post("/bulk-accept", response_model=InspectionBulkAcceptOut)
async def bulk_accept_inspections(
    data: InspectionBulkAcceptRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Массово принять обходы без единого замечания и без своей проверки —
    чтобы не нажимать «Принять» по одному на каждой из сотен «зелёных»
    площадок. Список id от клиента не считается доверенным: каждый обход
    здесь перепроверяется на сервере (статус/район/уже проверен кем-то),
    те, что не проходят проверку, просто пропускаются, а не валят весь
    запрос."""
    if current_user.role not in ("reviewer", "admin"):
        raise HTTPException(403, "Недостаточно прав")

    ids = [str(i) for i in data.ids]
    rows = (await db.execute(
        select(Inspection).where(Inspection.id.in_(ids)).options(
            selectinload(Inspection.site).selectinload(Site.courtyard),
        )
    )).scalars().all()

    issue_counts = dict((await db.execute(
        select(Issue.inspection_id, func.count())
        .where(Issue.inspection_id.in_(ids))
        .group_by(Issue.inspection_id)
    )).all())

    now = datetime.now(timezone.utc)
    accepted = 0
    skipped = len(ids) - len(rows)  # id, которых вообще не нашли в базе
    for obj in rows:
        district_id = obj.site.courtyard.district_id if obj.site and obj.site.courtyard else None
        eligible = (
            obj.status == "completed"
            and obj.reviewed_by is None
            and issue_counts.get(obj.id, 0) == 0
            and in_district_scope(current_user, district_id)
        )
        if not eligible:
            skipped += 1
            continue
        obj.reviewed_by = current_user.id
        obj.reviewed_at = now
        accepted += 1

    if accepted:
        await log_action(db, str(current_user.id), "inspection_bulk_accept", "inspection", None, {
            "accepted": accepted, "skipped": skipped,
        })
    await db.commit()
    return InspectionBulkAcceptOut(accepted=accepted, skipped=skipped)


@router.get("/{inspection_id}", response_model=InspectionOut)
async def get_inspection(
    inspection_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Inspection).where(Inspection.id == inspection_id).options(
        selectinload(Inspection.site).selectinload(Site.courtyard).selectinload(Courtyard.district),
        selectinload(Inspection.inspector),
        selectinload(Inspection.answers),
        selectinload(Inspection.reviewed_by_user),
    )
    obj = (await db.execute(q)).scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Обход не найден")

    if current_user.role == "inspector":
        check_own_or_role(current_user, obj.inspector_id, "reviewer", "admin")
    elif current_user.role == "reviewer":
        district_id = obj.site.courtyard.district_id if obj.site and obj.site.courtyard else None
        if not in_district_scope(current_user, district_id):
            raise HTTPException(403, "Обход вне вашего района")

    return await _inspection_to_out(obj, db)


@router.patch("/{inspection_id}", response_model=InspectionOut)
async def update_inspection(
    inspection_id: str,
    data: InspectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obj = (await db.execute(
        select(Inspection).where(Inspection.id == inspection_id).options(
            selectinload(Inspection.site).selectinload(Site.courtyard),
        )
    )).scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Обход не найден")
    check_own_or_role(current_user, obj.inspector_id, "reviewer", "admin")
    if current_user.role == "reviewer":
        district_id = obj.site.courtyard.district_id if obj.site and obj.site.courtyard else None
        if not in_district_scope(current_user, district_id):
            raise HTTPException(403, "Обход вне вашего района")

    if data.status:
        # Общее фото площадки обязательно при завершении обхода самим
        # инспектором — фронтенд уже блокирует кнопки "Завершить" без него
        # (см. generalPhotos в InspectionPage.tsx), но бэкенд эту проверку
        # не дублировал, и прямой вызов PATCH мог завершить обход вообще
        # без единого фото. Проверяем только когда статус меняет сам
        # владелец-инспектор — у reviewer/admin (приём/возврат обхода) это
        # не проверка завершения, а отдельное действие без такого UI-гейта.
        if (data.status in ("completed", "issues_found", "critical")
                and str(obj.inspector_id) == str(current_user.id)):
            general_photo_count = (await db.execute(
                select(func.count()).select_from(Photo).where(
                    Photo.inspection_id == obj.id, Photo.target_type == "inspection",
                )
            )).scalar_one()
            if general_photo_count == 0:
                raise HTTPException(400, "Общее фото площадки обязательно перед завершением обхода")
        obj.status = data.status
        if data.status in ("completed", "issues_found", "critical"):
            obj.completed_at = datetime.now(timezone.utc)
    if data.comment is not None:
        obj.comment = data.comment
    # Только reviewer/admin — иначе владелец-инспектор (check_own_or_role
    # выше пускает и его) мог бы сам стереть/подделать комментарий
    # проверяющего, например скрыть, что обход вернули на доработку.
    if data.reviewer_comment is not None and current_user.role in ("reviewer", "admin"):
        obj.reviewer_comment = data.reviewer_comment
    if data.gps_lat is not None:
        obj.gps_lat = data.gps_lat
    if data.gps_lon is not None:
        obj.gps_lon = data.gps_lon

    # Если reviewer/admin меняет статус — фиксируем кто и когда проверил
    if current_user.role in ("reviewer", "admin") and data.status:
        obj.reviewed_by = current_user.id
        obj.reviewed_at = datetime.now(timezone.utc)
        await log_action(db, str(current_user.id), "inspection_review", "inspection", inspection_id, {
            "status": data.status, "reviewer_comment": data.reviewer_comment,
        })

    if data.answers:
        for ans in data.answers:
            existing = (await db.execute(
                select(ChecklistAnswer).where(
                    ChecklistAnswer.inspection_id == inspection_id,
                    ChecklistAnswer.checklist_item_id == str(ans.checklist_item_id),
                )
            )).scalar_one_or_none()
            if existing:
                existing.result = ans.result
                existing.comment = ans.comment
            else:
                db.add(ChecklistAnswer(
                    inspection_id=inspection_id,
                    checklist_item_id=str(ans.checklist_item_id),
                    result=ans.result,
                    comment=ans.comment,
                ))

    # Пункты чек-листа с requires_photo=TRUE (например «Фото общего вида
    # площадки») были помечены как обязательные к фото ещё в schema.sql, но
    # это никогда не проверялось — обход можно было завершить вообще без
    # этих фото. Проверяем после апсерта ответов выше (autoflush делает
    # только что добавленные/обновлённые ChecklistAnswer видимыми для
    # запроса ниже) и, как и общее фото площадки, только когда статус
    # меняет сам владелец-инспектор.
    if (data.status in ("completed", "issues_found", "critical")
            and str(obj.inspector_id) == str(current_user.id)):
        missing_photo_items = (await db.execute(
            select(ChecklistItem.question)
            .join(ChecklistAnswer, ChecklistAnswer.checklist_item_id == ChecklistItem.id)
            .outerjoin(Photo, Photo.checklist_answer_id == ChecklistAnswer.id)
            .where(
                ChecklistAnswer.inspection_id == inspection_id,
                ChecklistItem.requires_photo.is_(True),
                Photo.id.is_(None),
            )
        )).scalars().all()
        if missing_photo_items:
            raise HTTPException(400, f"Нужно фото для пункта(ов) чек-листа: {', '.join(missing_photo_items)}")

    await db.commit()

    # Перезагружаем с eager-load для _inspection_to_out (db.refresh не подтягивает
    # связи, а обращение к ним лениво вне greenlet-контекста async-сессии падает
    # с MissingGreenlet)
    q = select(Inspection).where(Inspection.id == obj.id).options(
        selectinload(Inspection.site).selectinload(Site.courtyard).selectinload(Courtyard.district),
        selectinload(Inspection.inspector),
        selectinload(Inspection.answers),
        selectinload(Inspection.reviewed_by_user),
    )
    obj = (await db.execute(q)).scalar_one()
    return await _inspection_to_out(obj, db)


UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "uploads")

@router.post("/{inspection_id}/photos", response_model=PhotoOut)
async def upload_inspection_photo(
    inspection_id: str,
    file: UploadFile = File(...),
    gps_lat: Optional[float] = Query(None),
    gps_lon: Optional[float] = Query(None),
    taken_at: Optional[datetime] = Query(None),
    checklist_answer_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Загрузить фото для обхода или конкретного пункта чек-листа."""
    obj = (await db.execute(
        select(Inspection).where(Inspection.id == inspection_id).options(
            selectinload(Inspection.site).selectinload(Site.courtyard),
        )
    )).scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Обход не найден")

    # Проверяем права
    check_own_or_role(current_user, obj.inspector_id, "reviewer", "admin")
    if current_user.role == "reviewer":
        district_id = obj.site.courtyard.district_id if obj.site and obj.site.courtyard else None
        if not in_district_scope(current_user, district_id):
            raise HTTPException(403, "Обход вне вашего района")

    target_type = "checklist_answer" if checklist_answer_id else "inspection"

    # Сохраняем файл (потоково, с проверкой размера — file.size ненадёжен,
    # если клиент не прислал Content-Length)
    ext = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "jpg"
    safe_ext = ext.lower()[:5]
    filename = f"{_uuid.uuid4()}.{safe_ext}"
    rel_path = os.path.join("inspections", filename)
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
        target_type=target_type,
        inspection_id=obj.id,
        checklist_answer_id=checklist_answer_id if checklist_answer_id else None,
        storage_path=rel_path,
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        taken_at=taken_at,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return _photo_to_out(photo)


@router.get("/{inspection_id}/photos", response_model=list[PhotoOut])
async def list_inspection_photos(
    inspection_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obj = (await db.execute(
        select(Inspection).where(Inspection.id == inspection_id).options(
            selectinload(Inspection.site).selectinload(Site.courtyard),
        )
    )).scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Обход не найден")
    if current_user.role == "inspector":
        check_own_or_role(current_user, obj.inspector_id, "reviewer", "admin")
    elif current_user.role == "reviewer":
        district_id = obj.site.courtyard.district_id if obj.site and obj.site.courtyard else None
        if not in_district_scope(current_user, district_id):
            raise HTTPException(403, "Обход вне вашего района")

    q = select(Photo).where(
        Photo.inspection_id == inspection_id,
        Photo.target_type.in_(["inspection", "checklist_answer"]),
    ).order_by(Photo.created_at.asc())
    rows = (await db.execute(q)).scalars().all()
    return [_photo_to_out(p) for p in rows]


async def _inspection_to_out(
    i: Inspection, db: AsyncSession,
    _issues_count: Optional[int] = None, _photos: Optional[list] = None,
) -> InspectionOut:
    # _issues_count/_photos — предзагруженные значения для списков (см.
    # list_inspections): без них список из page_size=1000 (карта грузит
    # именно столько на каждого инспектора/район) делал бы 2 доп. запроса
    # НА КАЖДУЮ строку — до ~2000 последовательных запросов на один заход
    # на карту. Одиночные вызовы (get/create/update одного обхода) как и
    # раньше считают на месте.
    if _issues_count is not None:
        issues_count = _issues_count
    else:
        issues_count = (await db.execute(
            select(func.count()).select_from(Issue).where(Issue.inspection_id == i.id)
        )).scalar_one() or 0

    if _photos is not None:
        photos = _photos
    else:
        photos_q = select(Photo).where(
            Photo.inspection_id == i.id,
            Photo.target_type.in_(["inspection", "checklist_answer"]),
        ).order_by(Photo.created_at.asc())
        photos = (await db.execute(photos_q)).scalars().all()

    reviewer = UserOut.model_validate(i.reviewed_by_user) if i.reviewed_by_user else None

    return InspectionOut(
        id=i.id,
        site_id=i.site_id,
        inspector=UserOut.model_validate(i.inspector),
        type=i.type,
        status=i.status,
        started_at=i.started_at,
        completed_at=i.completed_at,
        gps_lat=i.gps_lat,
        gps_lon=i.gps_lon,
        comment=i.comment,
        reviewer_comment=i.reviewer_comment,
        reviewed_by=reviewer,
        reviewed_at=i.reviewed_at,
        created_at=i.created_at,
        site=SiteOut(
            id=i.site.id, type=i.site.type, area_m2=i.site.area_m2,
            courtyard=CourtyardOut.model_validate(i.site.courtyard),
            district=DistrictOut.model_validate(i.site.courtyard.district),
            is_active=i.site.is_active,
            lat=None, lon=None,  # инспекции не вычисляют геометрию
        ),
        answers=[ChecklistAnswerOut.model_validate(a) for a in (i.answers or [])],
        issues_count=issues_count,
        photos_count=len(photos),
        photos=[_photo_to_out(p) for p in photos],
    )


def _photo_to_out(p: Photo) -> PhotoOut:
    return PhotoOut(
        id=p.id,
        target_type=p.target_type,
        inspection_id=p.inspection_id,
        issue_id=p.issue_id,
        checklist_answer_id=p.checklist_answer_id,
        url=f"/uploads/{p.storage_path}",
        thumbnail_url=f"/uploads/{p.thumbnail_path}" if p.thumbnail_path else None,
        gps_lat=p.gps_lat,
        gps_lon=p.gps_lon,
        taken_at=p.taken_at,
        created_at=p.created_at,
    )
