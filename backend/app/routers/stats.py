"""Statistics v2 API: one contract for dashboards and exports."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.schemas import StatsCategoriesOut, StatsDashboardOut, StatsDynamicsOut
from app.services.permissions import require_role
from app.services.statistics import StatisticsService
from app.services.statistics.filters import build_filter
from app.services.statistics.pptx import render_shtab

router = APIRouter()


def _service(db, user, date_from, date_to, district_id, *, previous_week=False):
    return StatisticsService(
        db,
        build_filter(user, date_from, date_to, district_id, default_previous_week=previous_week),
    )


@router.get("/dashboard", response_model=StatsDashboardOut)
async def dashboard(
    date_from: date | None = Query(None), date_to: date | None = Query(None),
    district_id: UUID | None = Query(None), db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("reviewer", "admin")),
):
    return await _service(db, current_user, date_from, date_to, district_id).dashboard()


@router.get("/dynamics", response_model=StatsDynamicsOut)
async def dynamics(
    date_from: date | None = Query(None), date_to: date | None = Query(None),
    district_id: UUID | None = Query(None), db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("reviewer", "admin")),
):
    return await _service(db, current_user, date_from, date_to, district_id).dynamics()


@router.get("/categories", response_model=StatsCategoriesOut)
async def categories(
    date_from: date | None = Query(None), date_to: date | None = Query(None),
    district_id: UUID | None = Query(None), db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("reviewer", "admin")),
):
    return await _service(db, current_user, date_from, date_to, district_id).categories()


@router.get("/shtab.pptx")
async def shtab_pptx(
    date_from: date | None = Query(None), date_to: date | None = Query(None),
    district_id: UUID | None = Query(None), db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("reviewer", "admin")),
):
    service = _service(
        db, current_user, date_from, date_to, district_id, previous_week=True
    )
    dashboard_data = await service.dashboard()
    category_data = await service.categories()
    filename = (
        f"shtab_{dashboard_data.period.date_from.isoformat()}_"
        f"{dashboard_data.period.date_to.isoformat()}.pptx"
    )
    return StreamingResponse(
        render_shtab(dashboard_data, category_data),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
