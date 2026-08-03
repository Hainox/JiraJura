"""Issues router."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Issue, IssueStatusHistory, User
from app.schemas import IssueCreate, IssueUpdate, IssueOut, IssueListOut
from app.services.auth import get_current_user

router = APIRouter()


@router.post("/", response_model=IssueOut)
async def create_issue(
    data: IssueCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    issue = Issue(
        inspection_id=data.inspection_id,
        site_id=data.inspection_id,  # будет переопределено ниже
        title=data.title,
        description=data.description,
        criticality=data.criticality,
        status="open",
        created_by=current_user.id,
    )

    # подтягиваем site_id из обхода
    from app.models import Inspection
    insp = (await db.execute(
        select(Inspection).where(Inspection.id == data.inspection_id)
    )).scalar_one_or_none()
    if not insp:
        raise HTTPException(404, "Обход не найден")
    issue.site_id = insp.site_id

    db.add(issue)
    await db.commit()
    await db.refresh(issue)
    return IssueOut.model_validate(issue)


@router.get("/", response_model=IssueListOut)
async def list_issues(
    site_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    criticality: Optional[str] = Query(None),
    district_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    base = select(Issue).order_by(Issue.created_at.desc())

    if site_id:
        base = base.where(Issue.site_id == site_id)
    if status:
        base = base.where(Issue.status == status)
    if criticality:
        base = base.where(Issue.criticality == criticality)
    if district_id:
        from app.models import Site, Courtyard
        base = base.join(Site, Issue.site_id == Site.id).join(
            Courtyard, Site.courtyard_id == Courtyard.id
        ).where(Courtyard.district_id == district_id)

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    rows = (await db.execute(base.offset(offset).limit(page_size))).scalars().all()

    return IssueListOut(
        total=total,
        items=[IssueOut.model_validate(r) for r in rows],
    )


@router.get("/{issue_id}", response_model=IssueOut)
async def get_issue(issue_id: str, db: AsyncSession = Depends(get_db)):
    issue = (await db.execute(select(Issue).where(Issue.id == issue_id))).scalar_one_or_none()
    if not issue:
        raise HTTPException(404, "Замечание не найдено")
    return IssueOut.model_validate(issue)


@router.put("/{issue_id}", response_model=IssueOut)
async def update_issue(
    issue_id: str,
    data: IssueUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    issue = (await db.execute(select(Issue).where(Issue.id == issue_id))).scalar_one_or_none()
    if not issue:
        raise HTTPException(404, "Замечание не найдено")

    old_status = issue.status

    if data.status and data.status != issue.status:
        issue.status = data.status
        if data.status == "fixed":
            issue.fixed_at = datetime.utcnow()

        # запись в историю
        db.add(IssueStatusHistory(
            issue_id=issue_id,
            old_status=old_status,
            new_status=data.status,
            changed_by=current_user.id,
            comment=data.comment,
        ))

    if data.assigned_to is not None:
        issue.assigned_to = data.assigned_to
    if data.due_date is not None:
        issue.due_date = data.due_date

    issue.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(issue)
    return IssueOut.model_validate(issue)
