"""Audit log router — только для admin."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.database import get_db
from app.models import User
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
