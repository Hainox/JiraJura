"""Sites router."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Site, Courtyard, District, User
from app.schemas import SiteOut, SiteListOut, DistrictOut, CourtyardOut, ChecklistTemplateOut, UserOut, SiteAssignUpdate, SiteAdminUpdate
from app.services.auth import get_current_user
from app.services.permissions import require_role, in_district_scope
from app.services.audit import log_action

router = APIRouter()


@router.get("/", response_model=SiteListOut)
async def list_sites(
    district_id: Optional[str] = Query(None),
    courtyard_id: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    assigned_to_me: bool = Query(False),
    include_inactive: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Читаем уже посчитанную Postgres'ом GENERATED-колонку (см. Site.centroid
    # в models.py), а не пересчитываем ST_Centroid(geometry) на каждый
    # запрос — для list_sites с page_size до 5000 это была тысяча лишних
    # вычислений центроида на один список площадок.
    centroid_lat = func.ST_Y(Site.centroid).label("centroid_lat")
    centroid_lon = func.ST_X(Site.centroid).label("centroid_lon")

    base = (
        select(Site, centroid_lat, centroid_lon)
        .join(Courtyard, Site.courtyard_id == Courtyard.id)
        .join(District, Courtyard.district_id == District.id)
        .options(
            selectinload(Site.courtyard).selectinload(Courtyard.district),
            selectinload(Site.courtyard),
            selectinload(Site.assigned_inspector),
        )
    )
    # include_inactive — только для управления площадками в админ-панели;
    # всем остальным (карта/список для обходов) неактивные площадки
    # по-прежнему не показываются, даже если параметр передан.
    if not (include_inactive and current_user.role == "admin"):
        # Старые записи из БД могли быть созданы до NOT NULL/default для
        # is_active. NULL означает "не отключена", а не скрытую площадку.
        base = base.where(Site.is_active.is_not(False))

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

    if district_id and (
        current_user.role == "admin"
        or (current_user.role == "reviewer" and current_user.district_id is None)
    ):
        # Район пользователя берём только из БД, а не из query-параметра.
        # После смены района уже открытый клиент ещё некоторое время может
        # присылать старый district_id. Раньше сервер накладывал одновременно
        # новый район из current_user и старый район из URL, получал пустое
        # пересечение и площадки «исчезали» до повторного входа.
        # Явный фильтр нужен только админу и округ-wide проверяющему.
        base = base.where(District.id == district_id)
    if courtyard_id:
        base = base.where(Site.courtyard_id == courtyard_id)
    if type:
        base = base.where(Site.type == type)
    if search:
        base = base.where(Site.kml_original_id.ilike(f"%{search}%"))
    # "Мои назначенные площадки" — дополнительный фильтр только инспектора.
    # Проверяющий всегда видит все площадки своего района и назначает их
    # инспекторам, поэтому этот параметр не должен превращаться для него в
    # скрытое ограничение списка.
    if assigned_to_me and current_user.role == "inspector":
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
    # Читаем уже посчитанную Postgres'ом GENERATED-колонку (см. Site.centroid
    # в models.py) вместо пересчёта ST_Centroid(geometry) — см. list_sites.
    centroid_lat = func.ST_Y(Site.centroid).label("centroid_lat")
    centroid_lon = func.ST_X(Site.centroid).label("centroid_lon")

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


@router.patch("/{site_id}", response_model=SiteOut)
async def update_site(
    site_id: str,
    data: SiteAdminUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Редактирование метаданных площадки (тип/площадь/двор/активность) —
    геометрию тут не трогаем, для неё есть import_kml.py."""
    site = (await db.execute(select(Site).where(Site.id == site_id))).scalar_one_or_none()
    if not site:
        raise HTTPException(404, "Площадка не найдена")

    if data.courtyard_id is not None:
        courtyard = (await db.execute(select(Courtyard).where(Courtyard.id == data.courtyard_id))).scalar_one_or_none()
        if not courtyard:
            raise HTTPException(400, "Указанный двор не найден")
        site.courtyard_id = data.courtyard_id
    if data.type is not None:
        site.type = data.type
    if data.area_m2 is not None:
        site.area_m2 = data.area_m2
    if data.cleaning_type is not None:
        site.cleaning_type = data.cleaning_type
    if data.is_active is not None:
        site.is_active = data.is_active

    await log_action(db, str(current_user.id), "site_update", "site", site_id, data.model_dump(exclude_unset=True, mode="json"))
    await db.commit()

    q = (
        select(Site, func.ST_Y(Site.centroid), func.ST_X(Site.centroid))
        .where(Site.id == site_id)
        .options(selectinload(Site.courtyard).selectinload(Courtyard.district), selectinload(Site.assigned_inspector))
    )
    row = (await db.execute(q)).one()
    return _site_to_out(row[0], row[1], row[2])


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
        if not inspector or inspector.role != "inspector" or not inspector.is_active:
            raise HTTPException(400, "Указанный пользователь — не инспектор")

        site_district_id = site.courtyard.district_id if site.courtyard else None
        if inspector.district_id != site_district_id:
            raise HTTPException(
                400,
                "Инспектор и площадка должны относиться к одному району",
            )

    site.assigned_inspector_id = data.inspector_id
    await log_action(db, str(current_user.id), "site_assign", "site", site_id, {
        "assigned_inspector_id": str(data.inspector_id) if data.inspector_id else None,
    })
    await db.commit()

    q2 = (
        select(Site, func.ST_Y(Site.centroid), func.ST_X(Site.centroid))
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
    from app.schemas import ChecklistItemOut

    q = select(ChecklistTemplate).options(
        selectinload(ChecklistTemplate.items).selectinload(ChecklistItem.category_ref)
    )
    if site_type:
        q = q.where(ChecklistTemplate.site_type == site_type)
    templates = (await db.execute(q)).scalars().all()
    # Пункты, отключённые админом (is_active=False), не показываем в новых
    # обходах — только в самой админ-панели (GET /checklists/templates).
    return [
        ChecklistTemplateOut(
            id=t.id, name=t.name, site_type=t.site_type,
            items=[
                ChecklistItemOut(
                    id=i.id, category=i.category_ref.name if i.category_ref else i.category, category_id=i.category_id,
                    category_name=i.category_ref.name if i.category_ref else i.category,
                    question=i.question, sort_order=i.sort_order,
                    is_critical=i.is_critical, requires_photo=i.requires_photo,
                    is_active=i.is_active,
                )
                for i in sorted(t.items, key=lambda x: x.sort_order)
                if i.is_active
            ],
        )
        for t in templates
    ]


def _site_to_out(s: Site, lat: float | None = None, lon: float | None = None) -> SiteOut:
    return SiteOut(
        id=s.id,
        type=s.type,
        area_m2=s.area_m2,
        courtyard=CourtyardOut.model_validate(s.courtyard),
        district=DistrictOut.model_validate(s.courtyard.district),
        # Совместимость с legacy-строками, где is_active ещё был NULL:
        # отсутствие флага трактуем как активную площадку.
        is_active=s.is_active is not False,
        lat=float(lat) if lat is not None else None,
        lon=float(lon) if lon is not None else None,
        assigned_inspector=UserOut.model_validate(s.assigned_inspector) if s.assigned_inspector else None,
    )
