"""Districts router."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import District, Courtyard, Site, User, UserInvite
from app.schemas import DistrictOut, DistrictAdminOut, DistrictUpdate, DistrictMergeRequest
from app.services.auth import get_current_user
from app.services.permissions import require_role
from app.services.audit import log_action

router = APIRouter()


@router.get("/", response_model=list[DistrictOut])
async def list_districts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(District).order_by(District.name)

    # Инспектор без района — нет доступа (неполная настройка аккаунта);
    # проверяющий без района курирует весь округ, видит все районы (как в sites.py)
    if current_user.role == "inspector":
        if current_user.district_id is not None:
            q = q.where(District.id == current_user.district_id)
        else:
            return []
    elif current_user.role == "reviewer" and current_user.district_id is not None:
        q = q.where(District.id == current_user.district_id)

    result = await db.execute(q)
    return [DistrictOut.model_validate(d) for d in result.scalars().all()]


@router.get("/admin", response_model=list[DistrictAdminOut])
async def list_districts_admin(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Список районов с числом дворов/площадок — для админ-панели
    (управление районами, объединение задвоенных при импорте)."""
    q = (
        select(
            District.id, District.name,
            func.count(func.distinct(Courtyard.id)).label("courtyards_count"),
            func.count(Site.id).label("sites_count"),
        )
        .select_from(District)
        .outerjoin(Courtyard, Courtyard.district_id == District.id)
        .outerjoin(Site, Site.courtyard_id == Courtyard.id)
        .group_by(District.id, District.name)
        .order_by(District.name)
    )
    rows = (await db.execute(q)).all()
    return [
        DistrictAdminOut(id=r.id, name=r.name, courtyards_count=r.courtyards_count, sites_count=r.sites_count)
        for r in rows
    ]


@router.patch("/{district_id}", response_model=DistrictOut)
async def rename_district(
    district_id: str,
    data: DistrictUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    d = (await db.execute(select(District).where(District.id == district_id))).scalar_one_or_none()
    if not d:
        raise HTTPException(404, "Район не найден")
    d.name = data.name
    await log_action(db, str(current_user.id), "district_rename", "district", district_id, {"name": data.name})
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Район с таким названием уже существует")
    await db.refresh(d)
    return DistrictOut.model_validate(d)


@router.post("/{district_id}/merge", response_model=DistrictOut)
async def merge_district(
    district_id: str,
    data: DistrictMergeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Переносит все дворы (и их площадки) из district_id в
    into_district_id, затем удаляет опустевший district_id. Для
    задвоенных/битых районов, попавших так при импорте KML (например
    "Бескудниковский;Восточное Дегунино") — без этого чинить приходилось
    вручную через psql."""
    if str(district_id) == str(data.into_district_id):
        raise HTTPException(400, "Нельзя объединить район сам с собой")
    src = (await db.execute(select(District).where(District.id == district_id))).scalar_one_or_none()
    if not src:
        raise HTTPException(404, "Исходный район не найден")
    dst = (await db.execute(select(District).where(District.id == data.into_district_id))).scalar_one_or_none()
    if not dst:
        raise HTTPException(404, "Целевой район не найден")

    # Core-уровневые UPDATE/DELETE, а не ORM-присваивания/db.delete() на
    # загруженных объектах — иначе последующий db.delete(src) откатывает
    # c.district_id обратно в NULL. District.courtyards — relationship без
    # cascade="delete"/passive_deletes: при удалении src ORM по умолчанию
    # сама обнуляет district_id у ассоциированных дворов (чтобы не
    # нарушить FK), и это происходит ПОСЛЕ моего ручного присваивания —
    # значение перезаписывается молча, без ошибки. Core-запросы этот
    # механизм relationship-cascade не затрагивают вообще.
    courtyards = (await db.execute(select(Courtyard).where(Courtyard.district_id == district_id))).scalars().all()
    for c in courtyards:
        # Двор с таким же названием уже есть в целевом районе (например
        # если данные частично дублировались) — переносим его площадки
        # в существующий двор вместо переименования/конфликта UNIQUE(district_id, name)
        existing = (await db.execute(
            select(Courtyard).where(Courtyard.district_id == data.into_district_id, Courtyard.name == c.name)
        )).scalar_one_or_none()
        if existing:
            await db.execute(
                Site.__table__.update().where(Site.courtyard_id == c.id).values(courtyard_id=existing.id)
            )
            await db.execute(Courtyard.__table__.delete().where(Courtyard.id == c.id))
        else:
            await db.execute(
                Courtyard.__table__.update().where(Courtyard.id == c.id).values(district_id=data.into_district_id)
            )

    # users.district_id/user_invites.district_id тоже ссылаются на districts
    # (без ON DELETE) — если хоть один инспектор/проверяющий или неиспользованное
    # приглашение всё ещё числится за исходным районом, DELETE ниже упадёт
    # IntegrityError и весь merge молча откатится. Именно так объединение
    # реального задвоенного района могло не срабатывать раньше — переносим
    # ссылки на целевой район вместо того чтобы просто удалить исходный.
    await db.execute(User.__table__.update().where(User.district_id == district_id).values(district_id=data.into_district_id))
    await db.execute(UserInvite.__table__.update().where(UserInvite.district_id == district_id).values(district_id=data.into_district_id))

    await db.execute(District.__table__.delete().where(District.id == district_id))
    await log_action(db, str(current_user.id), "district_merge", "district", district_id, {
        "into_district_id": str(data.into_district_id), "courtyards_moved": len(courtyards),
    })
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Не удалось объединить районы — на исходный район всё ещё что-то ссылается")
    await db.refresh(dst)
    return DistrictOut.model_validate(dst)
