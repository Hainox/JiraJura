"""Inspections router."""
from datetime import datetime
from typing import Optional
import uuid as _uuid
import os

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models import (
    Inspection, Site, Courtyard, District, User,
    ChecklistAnswer, ChecklistItem, ChecklistTemplate, Photo, Issue,
)
from app.schemas import (
    InspectionCreate, InspectionUpdate, InspectionOut,
    InspectionListOut, ChecklistAnswerOut, SiteOut, UserOut,
    DistrictOut, CourtyardOut, PhotoOut,
)
from app.services.auth import get_current_user

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
        started_at=datetime.utcnow(),
    )
    db.add(inspection)
    await db.commit()

    # Перезагружаем с eager-load для _inspection_to_out
    q = select(Inspection).where(Inspection.id == inspection.id).options(
        selectinload(Inspection.site).selectinload(Site.courtyard).selectinload(Courtyard.district),
        selectinload(Inspection.inspector),
        selectinload(Inspection.answers),
    )
    inspection = (await db.execute(q)).scalar_one()
    return await _inspection_to_out(inspection, db)


@router.get("/", response_model=InspectionListOut)
async def list_inspections(
    site_id: Optional[str] = Query(None),
    inspector_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    base = select(Inspection).options(
        selectinload(Inspection.site).selectinload(Site.courtyard).selectinload(Courtyard.district),
        selectinload(Inspection.inspector),
        selectinload(Inspection.answers),
    ).order_by(Inspection.created_at.desc())

    if site_id:
        base = base.where(Inspection.site_id == site_id)
    if inspector_id:
        base = base.where(Inspection.inspector_id == inspector_id)
    if status:
        base = base.where(Inspection.status == status)

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    q = base.offset(offset).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    items = [await _inspection_to_out(i, db) for i in rows]
    return InspectionListOut(total=total, items=items)


@router.get("/{inspection_id}", response_model=InspectionOut)
async def get_inspection(inspection_id: str, db: AsyncSession = Depends(get_db)):
    q = select(Inspection).where(Inspection.id == inspection_id).options(
        selectinload(Inspection.site).selectinload(Site.courtyard).selectinload(Courtyard.district),
        selectinload(Inspection.inspector),
        selectinload(Inspection.answers),
    )
    obj = (await db.execute(q)).scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Обход не найден")
    return await _inspection_to_out(obj, db)


@router.patch("/{inspection_id}", response_model=InspectionOut)
async def update_inspection(
    inspection_id: str,
    data: InspectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obj = (await db.execute(select(Inspection).where(Inspection.id == inspection_id))).scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Обход не найден")
    if str(obj.inspector_id) != str(current_user.id) and current_user.role not in ("okrug_admin", "system_admin"):
        raise HTTPException(403, "Нет прав")

    if data.status:
        obj.status = data.status
        if data.status in ("completed", "issues_found", "critical"):
            obj.completed_at = datetime.utcnow()
    if data.comment is not None:
        obj.comment = data.comment
    if data.gps_lat is not None:
        obj.gps_lat = data.gps_lat
    if data.gps_lon is not None:
        obj.gps_lon = data.gps_lon

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

    await db.commit()
    await db.refresh(obj)
    return await _inspection_to_out(obj, db)


UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "uploads")

@router.post("/{inspection_id}/photos", response_model=PhotoOut)
async def upload_inspection_photo(
    inspection_id: str,
    file: UploadFile = File(...),
    gps_lat: Optional[float] = Query(None),
    gps_lon: Optional[float] = Query(None),
    taken_at: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Загрузить фото для обхода."""
    obj = (await db.execute(
        select(Inspection).where(Inspection.id == inspection_id)
    )).scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Обход не найден")

    # Проверяем права
    if str(obj.inspector_id) != str(current_user.id) and current_user.role not in ("okrug_admin", "system_admin"):
        raise HTTPException(403, "Нет прав")

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
        target_type="inspection",
        inspection_id=obj.id,
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
):
    q = select(Photo).where(
        Photo.inspection_id == inspection_id,
        Photo.target_type == "inspection",
    ).order_by(Photo.created_at.asc())
    rows = (await db.execute(q)).scalars().all()
    return [_photo_to_out(p) for p in rows]


async def _inspection_to_out(i: Inspection, db: AsyncSession) -> InspectionOut:
    issues_count = (await db.execute(
        select(func.count()).select_from(Issue).where(Issue.inspection_id == i.id)
    )).scalar_one() or 0

    photos_q = select(Photo).where(
        Photo.inspection_id == i.id, Photo.target_type == "inspection"
    ).order_by(Photo.created_at.asc())
    photos = (await db.execute(photos_q)).scalars().all()

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
        url=f"/uploads/{p.storage_path}",
        thumbnail_url=f"/uploads/{p.thumbnail_path}" if p.thumbnail_path else None,
        gps_lat=p.gps_lat,
        gps_lon=p.gps_lon,
        taken_at=p.taken_at,
        created_at=p.created_at,
    )
