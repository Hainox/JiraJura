"""Эксплуатационная сводка и инструменты для пункта меню "Разработчик" в
админ-панели — не новая роль, просто доп. пункт, видимый account'ам с
users.is_developer=true (см. is_developer в models.py/UserRoleUpdate)."""
import os
import re
import uuid as _uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models import (
    User, District, Courtyard, Site, Inspection, Issue, Photo, AuditLog,
)
from app.services.audit import log_action
from app.services.permissions import require_role

router = APIRouter()

_START_TIME = datetime.now(timezone.utc)
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "uploads")
_BCRYPT_RE = re.compile(r"^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$")


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


# ── Диагностика по клику — веб-обёртка над diagnose_logins.py и
# diagnose_missing_required_photos.py (те же самые SQL-запросы), чтобы не
# дёргать SSH ради типового разбора жалобы "не могу войти"/"не выходит
# завершить обход". Только чтение, ничего не меняет — режимы --apply тех
# скриптов (сброс пароля битым аккаунтам) сюда сознательно не вынесены:
# это не тот случай, где стоит экономить один SSH-заход ценой кнопки в
# проде без отдельного подтверждения.

class DiagnosticsLoginsOut(BaseModel):
    total_users: int
    broken_password_hash: list[dict]
    inactive_not_soft_deleted: list[dict]
    pending_registrations: list[dict]


@router.get("/diagnostics/logins", response_model=DiagnosticsLoginsOut)
async def diagnostics_logins(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_developer),
):
    rows = (await db.execute(text(
        "SELECT id, login, full_name, role, is_active, password_hash "
        "FROM users ORDER BY full_name"
    ))).fetchall()

    broken = []
    inactive_not_deleted = []
    for uid, login, full_name, role, is_active, pw_hash in rows:
        if not is_active:
            if not login.startswith("deleted_"):
                inactive_not_deleted.append({"login": login, "full_name": full_name})
            continue
        if not pw_hash or not _BCRYPT_RE.match(pw_hash):
            broken.append({"id": str(uid), "login": login, "full_name": full_name, "role": role})

    invites = (await db.execute(text(
        "SELECT login, full_name, expires_at FROM user_invites "
        "WHERE used_at IS NULL ORDER BY full_name"
    ))).fetchall()
    pending = [
        {"login": login, "full_name": full_name, "expires_at": expires_at.isoformat()}
        for login, full_name, expires_at in invites
    ]

    return DiagnosticsLoginsOut(
        total_users=len(rows),
        broken_password_hash=broken,
        inactive_not_soft_deleted=inactive_not_deleted,
        pending_registrations=pending,
    )


class DiagnosticsMissingPhotosOut(BaseModel):
    query_address: str
    query_district: str | None
    sites: list[dict]


@router.get("/diagnostics/missing-photos", response_model=DiagnosticsMissingPhotosOut)
async def diagnostics_missing_photos(
    address: str = Query(..., min_length=2),
    district: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_developer),
):
    params = {"address": f"%{address}%"}
    district_clause = ""
    if district:
        district_clause = "AND d.name ILIKE :district"
        params["district"] = f"%{district}%"

    sites = (await db.execute(text(
        "SELECT s.id, s.type, c.name AS courtyard_name, d.name AS district_name "
        "FROM sites s JOIN courtyards c ON c.id = s.courtyard_id "
        "JOIN districts d ON d.id = c.district_id "
        f"WHERE c.name ILIKE :address {district_clause} "
        "ORDER BY d.name, c.name"
    ), params)).fetchall()

    out_sites = []
    for site in sites:
        inspections = (await db.execute(text(
            "SELECT i.id, i.status, i.created_at, i.completed_at, i.reviewed_by, "
            "u.full_name AS inspector_name "
            "FROM inspections i JOIN users u ON u.id = i.inspector_id "
            "WHERE i.site_id = :site_id ORDER BY i.created_at DESC"
        ), {"site_id": site.id})).fetchall()

        out_inspections = []
        for insp in inspections:
            # Та же проверка, что делает backend перед разрешением завершить
            # обход (см. missing_photo_items в routers/inspections.py)
            missing = (await db.execute(text(
                "SELECT ci.question "
                "FROM checklist_answers ca "
                "JOIN checklist_items ci ON ci.id = ca.checklist_item_id "
                "LEFT JOIN photos p ON p.checklist_answer_id = ca.id "
                "WHERE ca.inspection_id = :insp_id AND ci.requires_photo = TRUE AND p.id IS NULL"
            ), {"insp_id": insp.id})).scalars().all()

            photos = (await db.execute(text(
                "SELECT p.id, p.target_type, p.created_at, p.taken_at, "
                "ci.question AS checklist_question, iss.title AS issue_title "
                "FROM photos p "
                "LEFT JOIN checklist_answers ca ON ca.id = p.checklist_answer_id "
                "LEFT JOIN checklist_items ci ON ci.id = ca.checklist_item_id "
                "LEFT JOIN issues iss ON iss.id = p.issue_id "
                "WHERE p.inspection_id = :insp_id "
                "OR p.issue_id IN (SELECT id FROM issues WHERE inspection_id = :insp_id) "
                "ORDER BY p.created_at"
            ), {"insp_id": insp.id})).fetchall()

            out_inspections.append({
                "id": str(insp.id),
                "status": insp.status,
                "created_at": insp.created_at.isoformat(),
                "completed_at": insp.completed_at.isoformat() if insp.completed_at else None,
                "inspector_name": insp.inspector_name,
                "reviewed": insp.reviewed_by is not None,
                "missing_checklist_items": list(missing),
                "photos": [
                    {
                        "target_type": p.target_type,
                        "label": p.checklist_question or p.issue_title or p.target_type,
                        "created_at": p.created_at.isoformat(),
                        "taken_at": p.taken_at.isoformat() if p.taken_at else None,
                    }
                    for p in photos
                ],
            })

        out_sites.append({
            "site_id": str(site.id),
            "type": site.type,
            "courtyard_name": site.courtyard_name,
            "district_name": site.district_name,
            "inspections": out_inspections,
        })

    return DiagnosticsMissingPhotosOut(
        query_address=address, query_district=district, sites=out_sites,
    )


# ── Деплой по клику ─────────────────────────────────────────────────────
#
# api не имеет доступа к docker-сокету и не исполняет команды хоста
# напрямую — это дало бы взломщику публичного веб-приложения root на
# сервере при любой дыре в авторизации. Вместо этого кнопка «Деплой»
# только пишет маркер "запрошен деплой" в тот же audit_log, которым уже
# пользуется журнал аудита; реальные git pull/build/up/alembic (тот же
# набор команд, что и ручное обновление по deploy/README.md, п.9)
# выполняет отдельный host-side watcher (deploy/scripts/deploy-watcher.sh),
# запускается по cron на самом сервере — вне любого контейнера, читает
# маркеры через list_deploy_requests.py и пишет результат через
# record_deploy_result.py (оба — backend/*.py, тот же паттерн, что и
# diagnose_logins.py: самодостаточные, читают DATABASE_URL напрямую).

class DeployRequestIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class DeployRequestOut(BaseModel):
    entity_id: str
    requested_at: datetime


@router.post("/deploy/request", response_model=DeployRequestOut)
async def request_deploy(
    data: DeployRequestIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_developer),
):
    entity_id = str(_uuid.uuid4())
    now = datetime.now(timezone.utc)
    await log_action(
        db, str(current_user.id), "deploy_requested", "deployment", entity_id,
        {"note": data.note, "requested_by_login": current_user.login},
    )
    await db.commit()
    return DeployRequestOut(entity_id=entity_id, requested_at=now)


class DeployEventOut(BaseModel):
    id: str
    action: str
    entity_id: str | None
    user_name: str | None
    details: str | None
    created_at: datetime


class DeployStatusOut(BaseModel):
    events: list[DeployEventOut]


@router.get("/deploy/status", response_model=DeployStatusOut)
async def deploy_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_developer),
):
    """Последние 40 событий деплоя (запросы и результаты вперемешку,
    сортировка по времени — фронтенд сопоставляет пары по entity_id)."""
    rows = (await db.execute(
        select(AuditLog)
        .options(selectinload(AuditLog.user))
        .where(AuditLog.entity_type == "deployment")
        .order_by(desc(AuditLog.created_at))
        .limit(40)
    )).scalars().all()
    return DeployStatusOut(events=[
        DeployEventOut(
            id=str(r.id), action=r.action, entity_id=r.entity_id,
            user_name=r.user.full_name if r.user else None,
            details=r.details, created_at=r.created_at,
        )
        for r in rows
    ])
