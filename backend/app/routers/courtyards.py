"""Courtyards router — admin-only management (список площадок остаётся в
sites.py; здесь только сами дворы: переименование, перенос в другой район)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Courtyard, District, Site, User
from app.schemas import CourtyardAdminOut, CourtyardUpdate
from app.services.permissions import require_role
from app.services.audit import log_action

router = APIRouter()


@router.get("/", response_model=list[CourtyardAdminOut])
async def list_courtyards(
    district_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    q = (
        select(Courtyard, District.name.label("district_name"), func.count(Site.id).label("sites_count"))
        .join(District, Courtyard.district_id == District.id)
        .outerjoin(Site, Site.courtyard_id == Courtyard.id)
        .group_by(Courtyard.id, District.name)
        .order_by(District.name, Courtyard.name)
    )
    if district_id:
        q = q.where(Courtyard.district_id == district_id)
    if search:
        q = q.where(Courtyard.name.ilike(f"%{search}%"))
    rows = (await db.execute(q)).all()
    return [
        CourtyardAdminOut(
            id=r.Courtyard.id, name=r.Courtyard.name, district_id=r.Courtyard.district_id,
            section=r.Courtyard.section, district_name=r.district_name, sites_count=r.sites_count,
        )
        for r in rows
    ]


@router.patch("/{courtyard_id}", response_model=CourtyardAdminOut)
async def update_courtyard(
    courtyard_id: str,
    data: CourtyardUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    c = (await db.execute(select(Courtyard).where(Courtyard.id == courtyard_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Двор не найден")
    if data.name is not None:
        c.name = data.name
    if data.district_id is not None:
        c.district_id = data.district_id
    if data.section is not None:
        # Пустая строка — это "снять участок" (двор размечен неверно или
        # ещё не размечен), а не буквальное значение "" в БД.
        c.section = data.section or None
    await log_action(db, str(current_user.id), "courtyard_update", "courtyard", courtyard_id, {
        "name": data.name, "district_id": str(data.district_id) if data.district_id else None,
        "section": data.section,
    })
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Двор с таким названием уже есть в этом районе")
    await db.refresh(c)

    q = (
        select(District.name, func.count(Site.id))
        .select_from(Courtyard)
        .join(District, Courtyard.district_id == District.id)
        .outerjoin(Site, Site.courtyard_id == Courtyard.id)
        .where(Courtyard.id == courtyard_id)
        .group_by(District.name)
    )
    district_name, sites_count = (await db.execute(q)).one()
    return CourtyardAdminOut(
        id=c.id, name=c.name, district_id=c.district_id, section=c.section,
        district_name=district_name, sites_count=sites_count,
    )
