"""Эксплуатационная сводка для пункта меню "Разработчик" в админ-панели —
не новая роль, просто доп. пункт, видимый account'ам с users.is_developer=true
(см. is_developer в models.py/UserRoleUpdate)."""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import (
    User, District, Courtyard, Site, Inspection, Issue, Photo,
)
from app.services.permissions import require_role

router = APIRouter()

_START_TIME = datetime.now(timezone.utc)
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "uploads")


def _require_developer(current_user: User = Depends(require_role("admin"))) -> User:
    if not current_user.is_developer:
        raise HTTPException(403, "Доступно только разработчику")
    return current_user


class SystemStatsOut(BaseModel):
    app_env: str
    db_ok: bool
    uptime_seconds: int
    counts: dict[str, int]
    uploads_size_mb: float


def _dir_size_bytes(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


@router.get("/stats", response_model=SystemStatsOut)
async def system_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_developer),
):
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    counts = {}
    for label, model in [
        ("users", User), ("districts", District), ("courtyards", Courtyard),
        ("sites", Site), ("inspections", Inspection), ("issues", Issue), ("photos", Photo),
    ]:
        counts[label] = (await db.execute(select(func.count()).select_from(model))).scalar_one()

    uploads_size_mb = round(_dir_size_bytes(UPLOAD_DIR) / (1024 * 1024), 1) if os.path.isdir(UPLOAD_DIR) else 0.0

    return SystemStatsOut(
        app_env=settings.APP_ENV,
        db_ok=db_ok,
        uptime_seconds=int((datetime.now(timezone.utc) - _START_TIME).total_seconds()),
        counts=counts,
        uploads_size_mb=uploads_size_mb,
    )
