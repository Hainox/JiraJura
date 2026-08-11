"""Обращения с публичной веб-формы (/feedback) — без авторизации на приём,
только очередь для ручного разбора admin/reviewer. См. FeedbackReport в
models.py — сознательно отдельная сущность от Issue: это жалоба
гражданина/сотрудника, а не находка инспектора при обходе.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import FeedbackReport, User
from app.schemas import FeedbackReportCreate, FeedbackReportUpdate, FeedbackReportOut, FeedbackReportListOut
from app.services.permissions import require_role

router = APIRouter()

# Простейшая защита от случайного/автоматического спама формы — реальный
# rate-limit по IP тут не делаем (отдельная задача, если станет проблемой),
# но обрезаем то, что явно не жалоба.
_STATUSES = ("new", "in_review", "resolved", "dismissed")


@router.post("/", response_model=FeedbackReportOut, status_code=201)
async def submit_feedback(
    data: FeedbackReportCreate,
    db: AsyncSession = Depends(get_db),
):
    """Публичный эндпоинт — без авторизации, заявитель может быть анонимным."""
    report = FeedbackReport(
        full_name=data.full_name or None,
        phone=data.phone or None,
        location_text=data.location_text or None,
        message=data.message,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return FeedbackReportOut.model_validate(report)


@router.get("/", response_model=FeedbackReportListOut)
async def list_feedback(
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("reviewer", "admin")),
):
    base = select(FeedbackReport)
    if status:
        base = base.where(FeedbackReport.status == status)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(
        base.order_by(FeedbackReport.status == "new", FeedbackReport.created_at.desc())
    )).scalars().all()
    return FeedbackReportListOut(total=total, items=[FeedbackReportOut.model_validate(r) for r in rows])


@router.patch("/{report_id}", response_model=FeedbackReportOut)
async def update_feedback(
    report_id: str,
    data: FeedbackReportUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("reviewer", "admin")),
):
    report = (await db.execute(
        select(FeedbackReport).where(FeedbackReport.id == report_id)
    )).scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Обращение не найдено")

    if data.status is not None:
        if data.status not in _STATUSES:
            raise HTTPException(400, f"Недопустимый статус: {data.status}")
        report.status = data.status
        if data.status in ("resolved", "dismissed") and report.resolved_at is None:
            report.resolved_at = datetime.now(timezone.utc)
        elif data.status in ("new", "in_review"):
            report.resolved_at = None
    if data.admin_comment is not None:
        report.admin_comment = data.admin_comment

    await db.commit()
    await db.refresh(report)
    return FeedbackReportOut.model_validate(report)
