"""Statistics v2 API: one contract for dashboards and exports."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.schemas import (
    StatsCategoriesOut, StatsDashboardOut, StatsDynamicsOut, StatsSectionsOut,
)
from app.services.permissions import require_role
from app.services.statistics import StatisticsService
from app.services.statistics.filters import build_filter
from app.services.statistics.pptx import render_shtab

router = APIRouter()


def _service(db, user, date_from, date_to, district_id, *, previous_week=False, all_time=False, site_type=None):
    return StatisticsService(
        db,
        build_filter(
            user, date_from, date_to, district_id,
            default_previous_week=previous_week, all_time=all_time, site_type=site_type,
        ),
    )


@router.get("/dashboard", response_model=StatsDashboardOut)
async def dashboard(
    date_from: date | None = Query(None), date_to: date | None = Query(None),
    district_id: UUID | None = Query(None), all_time: bool = Query(False),
    # Разбивка «Детская площадка» / «Спортивная площадка» — запрос со штаба
    # 26.08.2026 (Кануков Д.М.): главы хотят видеть эти цифры раздельно, не
    # одной суммой. Значение — как в enum site_type (schema.sql), не
    # проверяется отдельным Literal, чтобы не расходиться с sites.list,
    # который тоже принимает type свободной строкой.
    site_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("reviewer", "admin")),
):
    return await _service(db, current_user, date_from, date_to, district_id, all_time=all_time, site_type=site_type).dashboard()


@router.get("/sections", response_model=StatsSectionsOut)
async def sections(
    district_id: UUID = Query(...),
    date_from: date | None = Query(None), date_to: date | None = Query(None),
    all_time: bool = Query(False),
    # Свод по участкам внутри района — запрос районов для углублённого
    # самоконтроля (не для окружного штаба, формат dashboard не меняется).
    site_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("reviewer", "admin")),
):
    return await _service(db, current_user, date_from, date_to, district_id, all_time=all_time, site_type=site_type).sections()


@router.get("/dynamics", response_model=StatsDynamicsOut)
async def dynamics(
    date_from: date | None = Query(None), date_to: date | None = Query(None),
    district_id: UUID | None = Query(None), all_time: bool = Query(False),
    site_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("reviewer", "admin")),
):
    return await _service(db, current_user, date_from, date_to, district_id, all_time=all_time, site_type=site_type).dynamics()


@router.get("/categories", response_model=StatsCategoriesOut)
async def categories(
    date_from: date | None = Query(None), date_to: date | None = Query(None),
    district_id: UUID | None = Query(None), all_time: bool = Query(False),
    site_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("reviewer", "admin")),
):
    return await _service(db, current_user, date_from, date_to, district_id, all_time=all_time, site_type=site_type).categories()


@router.get("/shtab.pptx")
async def shtab_pptx(
    date_from: date | None = Query(None), date_to: date | None = Query(None),
    district_id: UUID | None = Query(None), all_time: bool = Query(False),
    site_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("reviewer", "admin")),
):
    service = _service(
        db, current_user, date_from, date_to, district_id,
        previous_week=True, all_time=all_time, site_type=site_type,
    )
    dashboard_data = await service.dashboard()
    category_data = await service.categories()
    suffix = ""
    if site_type == "Детская площадка":
        suffix = "_detskie"
    elif site_type == "Спортивная площадка":
        suffix = "_sportivnye"
    filename = (
        f"shtab{suffix}_{dashboard_data.period.date_from.isoformat()}_"
        f"{dashboard_data.period.date_to.isoformat()}.pptx"
    )
    return StreamingResponse(
        render_shtab(dashboard_data, category_data, site_type=site_type),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
