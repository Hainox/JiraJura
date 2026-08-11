"""Обращения с публичной веб-формы (/feedback) — без авторизации на приём,
только очередь для ручного разбора admin/reviewer. См. FeedbackReport в
models.py — сознательно отдельная сущность от Issue: это жалоба
гражданина/сотрудника, а не находка инспектора при обходе.
"""
import os
import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models import FeedbackReport, FeedbackAttachment, User
from app.schemas import (
    FeedbackReportCreate, FeedbackReportUpdate, FeedbackReportOut,
    FeedbackReportListOut, FeedbackAttachmentOut,
)
from app.services.permissions import require_role

router = APIRouter()

_STATUSES = ("new", "in_review", "resolved", "dismissed")
_REPORT_TYPES = ("site", "app", "other")

# Публичный эндпоинт без авторизации — белый список расширений вместо
# чёрного, чтобы нельзя было залить исполняемый файл на сервер.
_ALLOWED_EXTENSIONS = {
    "jpg", "jpeg", "png", "heic", "webp",
    "pdf", "doc", "docx", "xls", "xlsx", "csv", "txt",
}
_MAX_ATTACHMENTS_PER_REPORT = 5

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "uploads")


def _attachment_to_out(a: FeedbackAttachment) -> FeedbackAttachmentOut:
    return FeedbackAttachmentOut(
        id=a.id, url=f"/uploads/{a.storage_path}",
        original_filename=a.original_filename, content_type=a.content_type,
        size_bytes=a.size_bytes, created_at=a.created_at,
    )


def _report_to_out(r: FeedbackReport) -> FeedbackReportOut:
    return FeedbackReportOut(
        id=r.id, report_type=r.report_type, full_name=r.full_name, phone=r.phone,
        location_text=r.location_text, message=r.message, status=r.status,
        admin_comment=r.admin_comment, created_at=r.created_at, resolved_at=r.resolved_at,
        attachments=[_attachment_to_out(a) for a in (r.attachments or [])],
    )


@router.post("/", response_model=FeedbackReportOut, status_code=201)
async def submit_feedback(
    data: FeedbackReportCreate,
    db: AsyncSession = Depends(get_db),
):
    """Публичный эндпоинт — без авторизации, заявитель может быть анонимным."""
    report_type = data.report_type if data.report_type in _REPORT_TYPES else "site"
    report = FeedbackReport(
        report_type=report_type,
        full_name=data.full_name or None,
        phone=data.phone or None,
        location_text=data.location_text or None,
        message=data.message,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    # Не трогаем report.attachments — на свежесозданном объекте это
    # ленивая (expired-после-commit) relationship, и обращение к ней вне
    # eager-load вызвало бы MissingGreenlet в асинхронной сессии; у только
    # что созданного обращения вложений в любом случае ещё нет.
    return FeedbackReportOut(
        id=report.id, report_type=report.report_type, full_name=report.full_name,
        phone=report.phone, location_text=report.location_text, message=report.message,
        status=report.status, admin_comment=report.admin_comment,
        created_at=report.created_at, resolved_at=report.resolved_at, attachments=[],
    )


@router.post("/{report_id}/attachments", response_model=FeedbackAttachmentOut, status_code=201)
async def upload_feedback_attachment(
    report_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Публичный — прикрепить фото/файл к уже созданному обращению.
    Без авторизации, как и сама форма: заявитель может быть анонимным.
    """
    report = (await db.execute(
        select(FeedbackReport).where(FeedbackReport.id == report_id)
    )).scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Обращение не найдено")

    existing_count = (await db.execute(
        select(func.count()).select_from(FeedbackAttachment)
        .where(FeedbackAttachment.feedback_report_id == report_id)
    )).scalar_one()
    if existing_count >= _MAX_ATTACHMENTS_PER_REPORT:
        raise HTTPException(400, f"Не больше {_MAX_ATTACHMENTS_PER_REPORT} вложений на одно обращение")

    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Недопустимый тип файла: .{ext or '?'}")

    filename = f"{_uuid.uuid4()}.{ext}"
    rel_path = os.path.join("feedback", filename)
    abs_path = os.path.join(UPLOAD_DIR, rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    max_bytes = settings.MAX_PHOTO_SIZE_MB * 1024 * 1024
    size = 0
    with open(abs_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                f.close()
                os.remove(abs_path)
                raise HTTPException(413, f"Файл больше {settings.MAX_PHOTO_SIZE_MB} МБ")
            f.write(chunk)

    attachment = FeedbackAttachment(
        feedback_report_id=report_id,
        storage_path=rel_path,
        original_filename=file.filename,
        content_type=file.content_type,
        size_bytes=size,
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)
    return _attachment_to_out(attachment)


@router.get("/", response_model=FeedbackReportListOut)
async def list_feedback(
    status: Optional[str] = Query(None),
    report_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("reviewer", "admin")),
):
    filters = []
    if status:
        filters.append(FeedbackReport.status == status)
    if report_type:
        filters.append(FeedbackReport.report_type == report_type)

    total = (await db.execute(
        select(func.count()).select_from(FeedbackReport).where(*filters)
    )).scalar_one()
    rows = (await db.execute(
        select(FeedbackReport).options(selectinload(FeedbackReport.attachments))
        .where(*filters)
        .order_by(FeedbackReport.status == "new", FeedbackReport.created_at.desc())
    )).scalars().unique().all()
    return FeedbackReportListOut(total=total, items=[_report_to_out(r) for r in rows])


@router.patch("/{report_id}", response_model=FeedbackReportOut)
async def update_feedback(
    report_id: str,
    data: FeedbackReportUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("reviewer", "admin")),
):
    report = (await db.execute(
        select(FeedbackReport).where(FeedbackReport.id == report_id)
        .options(selectinload(FeedbackReport.attachments))
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
    return _report_to_out(report)
