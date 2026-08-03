"""Reports router."""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import District, Courtyard, Site, Inspection, Issue
from app.schemas import ReportWeeklyOut, ReportMonthlyOut

router = APIRouter()


@router.get("/weekly", response_model=list[ReportWeeklyOut])
async def weekly_report(
    district_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    week_ago = datetime.utcnow() - timedelta(days=7)
    results = []

    dist_q = select(District).order_by(District.name)
    if district_id:
        dist_q = dist_q.where(District.id == district_id)
    districts = (await db.execute(dist_q)).scalars().all()

    for d in districts:
        court_ids = (
            await db.execute(select(Courtyard.id).where(Courtyard.district_id == d.id))
        ).scalars().all()
        court_ids = [str(c) for c in court_ids]

        total_sites = (await db.execute(
            select(func.count()).select_from(Site).where(
                Site.courtyard_id.in_(court_ids), Site.is_active
            )
        )).scalar_one() or 0

        inspected = (await db.execute(
            select(func.count()).select_from(Inspection).where(
                Inspection.site_id.in_(
                    select(Site.id).where(Site.courtyard_id.in_(court_ids))
                ),
                Inspection.created_at >= week_ago,
            )
        )).scalar_one() or 0

        issues_open = (await db.execute(
            select(func.count()).select_from(Issue).where(
                Issue.site_id.in_(
                    select(Site.id).where(Site.courtyard_id.in_(court_ids))
                ),
                Issue.status.in_(["open", "assigned", "in_work"]),
            )
        )).scalar_one() or 0

        issues_overdue = (await db.execute(
            select(func.count()).select_from(Issue).where(
                Issue.site_id.in_(
                    select(Site.id).where(Site.courtyard_id.in_(court_ids))
                ),
                Issue.status == "overdue",
            )
        )).scalar_one() or 0

        results.append(ReportWeeklyOut(
            district_id=d.id,
            district_name=d.name,
            total_sites=total_sites,
            inspected_sites=inspected,
            issues_open=issues_open,
            issues_overdue=issues_overdue,
        ))

    return results


@router.get("/monthly", response_model=list[ReportMonthlyOut])
async def monthly_report(
    district_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    month_ago = datetime.utcnow() - timedelta(days=30)
    results = []

    dist_q = select(District).order_by(District.name)
    if district_id:
        dist_q = dist_q.where(District.id == district_id)
    districts = (await db.execute(dist_q)).scalars().all()

    for d in districts:
        court_ids = (
            await db.execute(select(Courtyard.id).where(Courtyard.district_id == d.id))
        ).scalars().all()
        court_ids = [str(c) for c in court_ids]

        site_sub = select(Site.id).where(Site.courtyard_id.in_(court_ids))

        total_sites = (await db.execute(
            select(func.count()).select_from(Site).where(Site.courtyard_id.in_(court_ids), Site.is_active)
        )).scalar_one() or 0

        inspected = (await db.execute(
            select(func.count()).select_from(Inspection).where(
                Inspection.site_id.in_(site_sub),
                Inspection.created_at >= month_ago,
            )
        )).scalar_one() or 0

        created = (await db.execute(
            select(func.count()).select_from(Issue).where(
                Issue.site_id.in_(site_sub), Issue.created_at >= month_ago
            )
        )).scalar_one() or 0

        closed = (await db.execute(
            select(func.count()).select_from(Issue).where(
                Issue.site_id.in_(site_sub), Issue.status == "closed",
                Issue.updated_at >= month_ago,
            )
        )).scalar_one() or 0

        overdue = (await db.execute(
            select(func.count()).select_from(Issue).where(
                Issue.site_id.in_(site_sub), Issue.status == "overdue"
            )
        )).scalar_one() or 0

        results.append(ReportMonthlyOut(
            district_id=d.id,
            district_name=d.name,
            total_sites=total_sites,
            inspected_sites=inspected,
            issues_created=created,
            issues_closed=closed,
            issues_overdue=overdue,
        ))

    return results
