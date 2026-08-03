"""Sites router."""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Site, Courtyard, District
from app.schemas import SiteOut, SiteListOut, DistrictOut, CourtyardOut, ChecklistTemplateOut

router = APIRouter()


@router.get("/", response_model=SiteListOut)
async def list_sites(
    district_id: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
):
    centroid_lat = func.ST_Y(func.ST_Centroid(Site.geometry)).label("centroid_lat")
    centroid_lon = func.ST_X(func.ST_Centroid(Site.geometry)).label("centroid_lon")

    base = (
        select(Site, centroid_lat, centroid_lon)
        .join(Courtyard, Site.courtyard_id == Courtyard.id)
        .join(District, Courtyard.district_id == District.id)
        .options(
            selectinload(Site.courtyard).selectinload(Courtyard.district),
            selectinload(Site.courtyard),
        )
    )

    if district_id:
        base = base.where(District.id == district_id)
    if type:
        base = base.where(Site.type == type)
    if search:
        base = base.where(Site.kml_original_id.ilike(f"%{search}%"))

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
async def get_site(site_id: str, db: AsyncSession = Depends(get_db)):
    centroid_lat = func.ST_Y(func.ST_Centroid(Site.geometry)).label("centroid_lat")
    centroid_lon = func.ST_X(func.ST_Centroid(Site.geometry)).label("centroid_lon")

    q = (
        select(Site, centroid_lat, centroid_lon)
        .where(Site.id == site_id)
        .options(
            selectinload(Site.courtyard).selectinload(Courtyard.district),
            selectinload(Site.courtyard),
        )
    )
    row = (await db.execute(q)).one_or_none()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(404, "Площадка не найдена")
    return _site_to_out(row.Site, row.centroid_lat, row.centroid_lon)


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
    )
