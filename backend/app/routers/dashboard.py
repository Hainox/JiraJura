"""Dashboard router — сводная статистика."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, Inspection, Issue, Site, Courtyard, District
from app.services.auth import get_current_user

router = APIRouter()


class DashboardOut(BaseModel):
    total_sites: int = 0
    total_inspections_week: int = 0
    total_inspections_month: int = 0
    inspections_in_progress: int = 0
    inspections_reviewed: int = 0
    inspections_pending_review: int = 0
    issues_open: int = 0
    issues_overdue: int = 0
    inspectors_count: int = 0
    reviewers_count: int = 0


class DistrictStatOut(BaseModel):
    district_name: str
    total_sites: int
    inspected: int
    percent: float


@router.get("/", response_model=DashboardOut)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now = func.now()

    total_sites = (await db.execute(select(func.count()).select_from(Site).where(Site.is_active))).scalar_one()

    # обходы за неделю/месяц
    week_ago = func.now() - func.make_interval(0, 0, 0, 7)
    month_ago = func.now() - func.make_interval(0, 1)

    base_insp = select(Inspection)
    if current_user.role == "reviewer" and current_user.district_id:
        base_insp = base_insp.join(Site).join(Courtyard).where(Courtyard.district_id == current_user.district_id)

    total_week = (await db.execute(
        select(func.count()).select_from(base_insp.subquery()).where(Inspection.created_at >= week_ago)
    )).scalar_one() or 0

    total_month = (await db.execute(
        select(func.count()).select_from(base_insp.subquery()).where(Inspection.created_at >= month_ago)
    )).scalar_one() or 0

    in_progress = (await db.execute(
        select(func.count()).select_from(base_insp.subquery()).where(Inspection.status == "in_progress")
    )).scalar_one() or 0

    reviewed = (await db.execute(
        select(func.count()).select_from(base_insp.subquery()).where(Inspection.reviewed_by.isnot(None))
    )).scalar_one() or 0

    pending = (await db.execute(
        select(func.count()).select_from(base_insp.subquery()).where(
            Inspection.reviewed_by.is_(None), Inspection.status.in_(["completed", "issues_found", "critical"])
        )
    )).scalar_one() or 0

    # issues
    base_issue = select(Issue)
    if current_user.role == "reviewer" and current_user.district_id:
        base_issue = base_issue.join(Site).join(Courtyard).where(Courtyard.district_id == current_user.district_id)

    open_issues = (await db.execute(
        select(func.count()).select_from(base_issue.subquery()).where(Issue.status.in_(["open", "assigned", "in_work"]))
    )).scalar_one() or 0

    overdue = (await db.execute(
        select(func.count()).select_from(base_issue.subquery()).where(Issue.status == "overdue")
    )).scalar_one() or 0

    inspectors = (await db.execute(select(func.count()).select_from(User).where(User.role == "inspector", User.is_active))).scalar_one()
    reviewers = (await db.execute(select(func.count()).select_from(User).where(User.role == "reviewer", User.is_active))).scalar_one()

    return DashboardOut(
        total_sites=total_sites,
        total_inspections_week=total_week,
        total_inspections_month=total_month,
        inspections_in_progress=in_progress,
        inspections_reviewed=reviewed,
        inspections_pending_review=pending,
        issues_open=open_issues,
        issues_overdue=overdue,
        inspectors_count=inspectors,
        reviewers_count=reviewers,
    )


@router.get("/districts", response_model=list[DistrictStatOut])
async def get_district_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Статистика по районам: % обойденных площадок."""
    districts_res = (await db.execute(select(District))).scalars().all()
    result = []
    for d in districts_res:
        total = (await db.execute(
            select(func.count()).select_from(Site).join(Courtyard).where(Courtyard.district_id == d.id, Site.is_active)
        )).scalar_one() or 0

        inspected = (await db.execute(
            select(func.count()).select_from(Inspection).join(Site).join(Courtyard)
            .where(Courtyard.district_id == d.id, Inspection.status.in_(["completed", "issues_found", "critical"]))
        )).scalar_one() or 0

        result.append(DistrictStatOut(
            district_name=d.name,
            total_sites=total,
            inspected=inspected,
            percent=round(inspected / total * 100, 1) if total > 0 else 0,
        ))
    return sorted(result, key=lambda r: r.percent, reverse=True)
