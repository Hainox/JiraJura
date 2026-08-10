"""Sites router."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Site, Courtyard, District, User
from app.schemas import SiteOut, SiteListOut, DistrictOut, CourtyardOut, ChecklistTemplateOut, UserOut, SiteAssignUpdate
from app.services.auth import get_current_user
from app.services.permissions import require_role, in_district_scope
from app.services.audit import log_action

router = APIRouter()


@router.get("/", response_model=SiteListOut)
async def list_sites(
    district_id: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    assigned_to_me: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    centroid_lat = func.ST_Y(func.ST_Centroid(Site.geometry)).label("centroid_lat")
    centroid_lon = func.ST_X(func.ST_Centroid(Site.geometry)).label("centroid_lon")

    base = (
        select(Site, centroid_lat, centroid_lon)
        .join(Courtyard, Site.courtyard_id == Courtyard.id)
        .join(District, Courtyard.district_id == District.id)
        .where(Site.is_active)
        .options(
            selectinload(Site.courtyard).selectinload(Courtyard.district),
            selectinload(Site.courtyard),
            selectinload(Site.assigned_inspector),
        )
    )

    # Не-админы: инспектор видит только площадки своего района (без района —
    # ничего, это неполная настройка аккаунта). Проверяющий с district_id=NULL
    # намеренно курирует весь округ — фильтр не применяется, как в issues/reports.
    if current_user.role == "inspector":
        if current_user.district_id is not None:
            base = base.where(Courtyard.district_id == current_user.district_id)
        else:
            return SiteListOut(total=0, items=[])
    elif current_user.role == "reviewer" and current_user.district_id is not None:
        base = base.where(Courtyard.district_id == current_user.district_id)

    if district_id:
        # Дополнительно: если не-админ передал чужой district_id — игнорируем,
        # потому что ограничение по своему району уже применено выше
        base = base.where(District.id == district_id)
    if type:
        base = base.where(Site.type == type)
    if search:
        base = base.where(Site.kml_original_id.ilike(f"%{search}%"))
    # "Мои площадки" — не хард-ограничение доступа (см. комментарий у
    # assigned_inspector_id в models.py), просто фильтр вида, поэтому
    # доступен любой роли: инспектору — свои, проверяющему/админу — чтобы
    # проверить, что реально назначено конкретному человеку.
    if assigned_to_me:
        base = base.where(Site.assigned_inspector_id == current_user.id)

    # count
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # paginate
    offset = (page - 1) * page_size
    q = base.offset(offset).limit(page_size)
    rows = (await db.execute(q)).all()

    items = [_site_to_out(r.Site, r.centroid_lat, r.centroid_lon) for r in rows]
    return SiteListOut(total=total, items=items)


@router.get("/{site_id}", response_model=SiteOut)
async def get_site(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    centroid_lat = func.ST_Y(func.ST_Centroid(Site.geometry)).label("centroid_lat")
    centroid_lon = func.ST_X(func.ST_Centroid(Site.geometry)).label("centroid_lon")

    q = (
        select(Site, centroid_lat, centroid_lon)
        .join(Courtyard, Site.courtyard_id == Courtyard.id)
        .where(Site.id == site_id)
        .options(
            selectinload(Site.courtyard).selectinload(Courtyard.district),
            selectinload(Site.courtyard),
            selectinload(Site.assigned_inspector),
        )
    )

    # Не-админы: инспектор без района — нет доступа; проверяющий без района
    # курирует весь округ (см. list_sites)
    if current_user.role == "inspector":
        if current_user.district_id is not None:
            q = q.where(Courtyard.district_id == current_user.district_id)
        else:
            raise HTTPException(403, "Нет доступа к площадкам")
    elif current_user.role == "reviewer" and current_user.district_id is not None:
        q = q.where(Courtyard.district_id == current_user.district_id)

    row = (await db.execute(q)).one_or_none()
    if not row:
        raise HTTPException(404, "Площадка не найдена")
    return _site_to_out(row.Site, row.centroid_lat, row.centroid_lon)


@router.patch("/{site_id}/assign", response_model=SiteOut)
async def assign_site_inspector(
    site_id: str,
    data: SiteAssignUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("reviewer", "admin")),
):
    """Назначить площадку инспектору (или снять назначение — inspector_id=null).

    Ориентир для распределения обходов внутри района, не хард-ограничение:
    любой инспектор своего района по-прежнему может начать обход любой
    площадки (см. комментарий у Site.assigned_inspector_id).
    """
    q = (
        select(Site)
        .where(Site.id == site_id)
        .options(selectinload(Site.courtyard).selectinload(Courtyard.district))
    )
    site = (await db.execute(q)).scalar_one_or_none()
    if not site:
        raise HTTPException(404, "Площадка не найдена")

    if current_user.role == "reviewer":
        district_id = site.courtyard.district_id if site.courtyard else None
        if not in_district_scope(current_user, district_id):
            raise HTTPException(403, "Площадка вне вашего района")

    if data.inspector_id is not None:
        inspector = (await db.execute(
            select(User).where(User.id == data.inspector_id)
        )).scalar_one_or_none()
        if not inspector or inspector.role != "inspector":
            raise HTTPException(400, "Указанный пользователь — не инспектор")

    site.assigned_inspector_id = data.inspector_id
    await log_action(db, str(current_user.id), "site_assign", "site", site_id, {
        "assigned_inspector_id": str(data.inspector_id) if data.inspector_id else None,
    })
    await db.commit()

    q2 = (
        select(Site, func.ST_Y(func.ST_Centroid(Site.geometry)), func.ST_X(func.ST_Centroid(Site.geometry)))
        .where(Site.id == site_id)
        .options(
            selectinload(Site.courtyard).selectinload(Courtyard.district),
            selectinload(Site.assigned_inspector),
        )
    )
    row = (await db.execute(q2)).one()
    return _site_to_out(row[0], row[1], row[2])


@router.get("/templates/checklist", response_model=list[ChecklistTemplateOut])
async def list_checklist_templates(
    site_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    from app.models import ChecklistTemplate, ChecklistItem
    q = select(ChecklistTemplate).options(selectinload(ChecklistTemplate.items))
    if site_type:
        q = q.where(ChecklistTemplate.site_type == site_type)
    templates = (await db.execute(q)).scalars().all()
    return [ChecklistTemplateOut.model_validate(t) for t in templates]


def _site_to_out(s: Site, lat: float | None = None, lon: float | None = None) -> SiteOut:
    return SiteOut(
        id=s.id,
        type=s.type,
        area_m2=s.area_m2,
        courtyard=CourtyardOut.model_validate(s.courtyard),
        district=DistrictOut.model_validate(s.courtyard.district),
        is_active=s.is_active,
        lat=float(lat) if lat is not None else None,
        lon=float(lon) if lon is not None else None,
        assigned_inspector=UserOut.model_validate(s.assigned_inspector) if s.assigned_inspector else None,
    )
