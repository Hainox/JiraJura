"""Issues router."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Issue, IssueStatusHistory, Site, Courtyard, District, User
from app.schemas import IssueCreate, IssueUpdate, IssueOut, IssueListOut, UserOut
from app.services.auth import get_current_user
from app.services.permissions import require_role
from app.services.audit import log_action

router = APIRouter()


def _issue_to_out(i: Issue) -> IssueOut:
    """Преобразовать модель Issue в схему IssueOut с обогащёнными данными."""
    site_name = None
    district_name = None
    if i.site_ref:
        site_name = i.site_ref.courtyard.name if i.site_ref.courtyard else None
        if i.site_ref.courtyard and i.site_ref.courtyard.district:
            district_name = i.site_ref.courtyard.district.name

    return IssueOut(
        id=i.id,
        title=i.title,
        description=i.description,
        criticality=i.criticality,
        status=i.status,
        site_id=i.site_id,
        inspection_id=i.inspection_id,
        assigned_to=i.assigned_to,
        assigned_user=UserOut.model_validate(i.assigned_user) if i.assigned_user else None,
        due_date=i.due_date,
        created_by=i.created_by,
        creator=UserOut.model_validate(i.creator_ref) if hasattr(i, 'creator_ref') and i.creator_ref else None,
        site_name=site_name,
        district_name=district_name,
        created_at=i.created_at,
        updated_at=i.updated_at,
    )


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

    # перезагружаем с eager-load
    q = select(Issue).where(Issue.id == issue.id).options(
        selectinload(Issue.site_ref).selectinload(Site.courtyard).selectinload(Courtyard.district),
        selectinload(Issue.assigned_user),
        selectinload(Issue.creator_ref),
    )
    issue = (await db.execute(q)).scalar_one()
    return _issue_to_out(issue)


@router.get("/", response_model=IssueListOut)
async def list_issues(
    site_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    criticality: Optional[str] = Query(None),
    district_id: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base = select(Issue).options(
        selectinload(Issue.site_ref).selectinload(Site.courtyard).selectinload(Courtyard.district),
        selectinload(Issue.assigned_user),
        selectinload(Issue.creator_ref),
    ).order_by(Issue.created_at.desc())

    if site_id:
        base = base.where(Issue.site_id == site_id)
    if status:
        base = base.where(Issue.status == status)
    if criticality:
        base = base.where(Issue.criticality == criticality)
    if assigned_to:
        base = base.where(Issue.assigned_to == assigned_to)

    effective_district_id = district_id
    if current_user.role == "reviewer" and current_user.district_id is not None:
        effective_district_id = str(current_user.district_id)
    if current_user.role == "inspector":
        base = base.where(Issue.created_by == current_user.id)

    if effective_district_id:
        base = base.join(Site, Issue.site_id == Site.id).join(
            Courtyard, Site.courtyard_id == Courtyard.id
        ).where(Courtyard.district_id == effective_district_id)

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    rows = (await db.execute(base.offset(offset).limit(page_size))).scalars().all()

    return IssueListOut(
        total=total,
        items=[_issue_to_out(r) for r in rows],
    )


@router.get("/{issue_id}", response_model=IssueOut)
async def get_issue(issue_id: str, db: AsyncSession = Depends(get_db)):
    q = select(Issue).where(Issue.id == issue_id).options(
        selectinload(Issue.site_ref).selectinload(Site.courtyard).selectinload(Courtyard.district),
        selectinload(Issue.assigned_user),
        selectinload(Issue.creator_ref),
    )
    issue = (await db.execute(q)).scalar_one_or_none()
    if not issue:
        raise HTTPException(404, "Замечание не найдено")
    return _issue_to_out(issue)


@router.put("/{issue_id}", response_model=IssueOut)
async def update_issue(
    issue_id: str,
    data: IssueUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("reviewer", "admin")),
):
    issue = (await db.execute(
        select(Issue).where(Issue.id == issue_id).options(
            selectinload(Issue.site_ref).selectinload(Site.courtyard).selectinload(Courtyard.district),
            selectinload(Issue.assigned_user),
            selectinload(Issue.creator_ref),
        )
    )).scalar_one_or_none()
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
    await log_action(db, str(current_user.id), "issue_update", "issue", issue_id, {
        "status": data.status, "assigned_to": str(data.assigned_to) if data.assigned_to else None,
    })
    await db.commit()

    # перезагружаем
    q = select(Issue).where(Issue.id == issue_id).options(
        selectinload(Issue.site_ref).selectinload(Site.courtyard).selectinload(Courtyard.district),
        selectinload(Issue.assigned_user),
        selectinload(Issue.creator_ref),
    )
    issue = (await db.execute(q)).scalar_one()
    return _issue_to_out(issue)
