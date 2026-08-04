"""Сервис аудита — запись действий в таблицу audit_log."""
import json
from datetime import datetime

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User


async def log_action(
    db: AsyncSession,
    user_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    details: dict | None = None,
):
    """Записать действие в журнал аудита."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=json.dumps(details, ensure_ascii=False, default=str) if details else None,
        created_at=datetime.utcnow(),
    )
    db.add(entry)
    # не await db.commit() — вызывающая сторона сама закоммитит


async def list_audit_log(
    db: AsyncSession,
    user_id: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    page: int = 1,
    page_size: int = 50,
):
    """Получить записи аудита с фильтрами."""
    from sqlalchemy import func
    from sqlalchemy.orm import selectinload

    base = select(AuditLog).options(selectinload(AuditLog.user)).order_by(desc(AuditLog.created_at))

    if user_id:
        base = base.where(AuditLog.user_id == user_id)
    if action:
        base = base.where(AuditLog.action == action)
    if entity_type:
        base = base.where(AuditLog.entity_type == entity_type)

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    rows = (await db.execute(base.offset(offset).limit(page_size))).scalars().all()

    return total, rows
