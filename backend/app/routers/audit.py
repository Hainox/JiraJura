"""Audit log router — только для admin."""
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AuditLog, User
from app.schemas import UserOut
from app.services.auth import get_current_user
from app.services.permissions import require_role
from app.services.audit import list_audit_log

router = APIRouter()


class AuditLogOut(BaseModel):
    id: str
    user_id: str | None = None
    user_name: str | None = None
    action: str
    entity_type: str
    entity_id: str | None = None
    details: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditListOut(BaseModel):
    total: int
    items: list[AuditLogOut]


@router.get("/", response_model=AuditListOut)
async def get_audit_log(
    user_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    total, rows = await list_audit_log(
        db, user_id=user_id, action=action, entity_type=entity_type,
        page=page, page_size=page_size,
    )

    items = []
    for r in rows:
        items.append(AuditLogOut(
            id=str(r.id),
            user_id=str(r.user_id) if r.user_id else None,
            user_name=r.user.full_name if r.user else None,
            action=r.action,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            details=r.details,
            created_at=r.created_at,
        ))

    return AuditListOut(total=total, items=items)


@router.get("/logins", response_model=AuditListOut)
async def get_login_history(
    login: Optional[str] = Query(None),
    ip: Optional[str] = Query(None),
    result: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """История входов: записи login_success/login_failed из журнала аудита.

    Логин и IP лежат внутри details (JSON-строка), поэтому фильтруем через
    jsonb: details::jsonb ->> 'login' ILIKE '%...%' — регистронезависимо и с
    частичным совпадением (админ может искать по фрагменту логина или IP).
    """
    base = (
        select(AuditLog)
        .where(AuditLog.action.in_(["login_success", "login_failed"]))
        .order_by(desc(AuditLog.created_at))
    )
    if result == "success":
        base = base.where(AuditLog.action == "login_success")
    elif result == "failed":
        base = base.where(AuditLog.action == "login_failed")

    details = func.cast(AuditLog.details, JSONB)
    if login:
        base = base.where(details.op("->>")("login").ilike(f"%{login}%"))
    if ip:
        base = base.where(details.op("->>")("ip").ilike(f"%{ip}%"))

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    rows = (await db.execute(base.offset(offset).limit(page_size))).scalars().all()

    items = []
    for r in rows:
        items.append(AuditLogOut(
            id=str(r.id),
            user_id=str(r.user_id) if r.user_id else None,
            user_name=r.user.full_name if r.user else None,
            action=r.action,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            details=r.details,
            created_at=r.created_at,
        ))
    return AuditListOut(total=total, items=items)
