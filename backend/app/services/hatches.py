# -*- coding: utf-8 -*-
"""Журнал осмотра люков: общие правила, которые нужны и роутеру люков
(app/routers/hatches.py), и завершению обхода (update_inspection в
app/routers/inspections.py).

Осмотр люка — часть обычного ежедневного обхода площадки. Дефект люка
становится обычным замечанием (Issue) категории «Люки» этого же обхода с
критичностью critical (срок 1 день по ISSUE_SLA_DAYS) — дальше оно
проходит тот же цикл устранения, что и замечания по площадкам.
"""
import re
from datetime import date, datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Hatch, HatchCheck, Inspection, Issue, IssueCategory, IssueStatusHistory, Photo,
)
from app.services.issues import default_due_date
from app.services.statistics.definitions import ON_CHECK_STATUSES, OVERDUE_STATUSES

HATCH_CATEGORY_NAME = "Люки"
HATCH_ISSUE_CRITICALITY = "critical"

HATCH_STATES = ("ok", "shifted", "damaged", "missing", "sink")
DEFECT_STATES = tuple(s for s in HATCH_STATES if s != "ok")

# Короткие подписи — в плашках и таблице журнала; полные — на кнопках
# выбора состояния и в заголовке замечания (утверждённый макет).
HATCH_STATE_SHORT = {
    "ok": "Исправен",
    "shifted": "Крышка смещена",
    "damaged": "Крышка повреждена",
    "missing": "Крышка отсутствует",
    "sink": "Провал вокруг люка",
}
HATCH_STATE_FULL = {
    "ok": "Исправен",
    "shifted": "Крышка смещена / неплотно закрыта",
    "damaged": "Крышка повреждена",
    "missing": "Крышка отсутствует",
    "sink": "Провал / просадка вокруг люка",
}

def natural_key(value: str | None) -> tuple:
    """«2» < «2а» < «10» < «Б-1», «Участок 2» < «Участок 10»: строковая
    сортировка ставила бы «10» перед «2»."""
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.lower())
        for part in re.split(r"(\d+)", (value or "").strip())
    )


def hatch_label(hatch: Hatch) -> str:
    return f"Люк №{hatch.number}" + (f" · {hatch.owner}" if hatch.owner else "")


def issue_title(hatch: Hatch, state: str) -> str:
    return f"{hatch_label(hatch)}: {HATCH_STATE_FULL[state]}"[:300]


def issue_description(hatch: Hatch, check: HatchCheck) -> str | None:
    lines = []
    if hatch.location_note:
        lines.append(f"Расположение: {hatch.location_note}")
    if check.fenced is True:
        lines.append("Опасное место ограждено")
    elif check.fenced is False:
        lines.append("Опасное место не ограждено")
    if check.owner_ticket:
        lines.append(f"Заявка владельцу № {check.owner_ticket}")
    if check.comment:
        lines.append(check.comment)
    return "\n".join(lines) or None


def measures_text(check: HatchCheck) -> str:
    """Графа «Принятые меры» бумажного журнала — одной строкой."""
    parts = []
    if check.fenced is True:
        parts.append("ограждено")
    elif check.fenced is False and check.state != "ok":
        parts.append("не ограждено")
    if check.owner_ticket:
        parts.append(f"заявка № {check.owner_ticket}")
    if check.comment:
        parts.append(check.comment)
    return "; ".join(parts)


def fix_state(issue_status: str | None, due_date: date | None, today: date) -> str:
    """Графа «Устранено»: none — замечания нет (люк исправен), in_work,
    overdue, on_check (сдано на проверку), accepted (принято округом).
    «Просрочено» — по тем же статусам, что и во всей статистике
    (OVERDUE_STATUSES): сданное на проверку уже не считается просроченным."""
    if issue_status is None:
        return "none"
    if issue_status == "closed":
        return "accepted"
    if issue_status in ON_CHECK_STATUSES:
        return "on_check"
    if issue_status in OVERDUE_STATUSES and due_date is not None and due_date < today:
        return "overdue"
    return "in_work"


async def hatch_category(db: AsyncSession) -> IssueCategory:
    return (await db.execute(
        select(IssueCategory).where(IssueCategory.name == HATCH_CATEGORY_NAME)
    )).scalar_one()


async def sync_issue_for_check(
    db: AsyncSession, check: HatchCheck, hatch: Hatch, inspection: Inspection, user_id,
) -> None:
    """Привести замечание в соответствие с осмотром люка.

    Дефект без замечания — создать (в тот же момент, что и дефект пункта
    чек-листа в update_inspection); дефект с замечанием — обновить
    заголовок/описание. Люк снова «исправен» — нетронутое (open) замечание
    удаляется как ошибочная отметка; если по нему уже начали работу,
    оставляем: дефект был реальным, и история устранения важнее.
    """
    if check.state != "ok":
        if check.issue_id is None:
            category = await hatch_category(db)
            issue = Issue(
                inspection_id=inspection.id,
                site_id=inspection.site_id,
                category_id=category.id,
                title=issue_title(hatch, check.state),
                description=issue_description(hatch, check),
                criticality=HATCH_ISSUE_CRITICALITY,
                status="open",
                created_by=user_id,
                due_date=default_due_date(HATCH_ISSUE_CRITICALITY, category.name),
            )
            db.add(issue)
            await db.flush()
            check.issue_id = issue.id
        else:
            issue = await db.get(Issue, check.issue_id)
            if issue is not None:
                issue.title = issue_title(hatch, check.state)
                issue.description = issue_description(hatch, check)
                issue.updated_at = datetime.now(timezone.utc)
        return

    if check.issue_id is None:
        return
    status = (await db.execute(
        select(Issue.status).where(Issue.id == check.issue_id)
    )).scalar_one_or_none()
    if status != "open":
        return
    issue_id = check.issue_id
    check.issue_id = None
    await db.flush()
    # Core-DELETE, а не db.delete(issue): ORM при удалении родителя
    # пытается обнулить FK у загруженных детей (issue_status_history.issue_id
    # NOT NULL), а фото ошибочно отмеченного дефекта не должны остаться
    # висеть без замечания.
    await db.execute(delete(IssueStatusHistory).where(IssueStatusHistory.issue_id == issue_id))
    await db.execute(delete(Photo).where(Photo.issue_id == issue_id, Photo.target_type == "issue"))
    await db.execute(delete(Issue).where(Issue.id == issue_id))


async def inspection_has_hatch_issues(db: AsyncSession, inspection_id) -> bool:
    return (await db.execute(
        select(func.count()).select_from(HatchCheck).where(
            HatchCheck.inspection_id == inspection_id,
            HatchCheck.issue_id.is_not(None),
        )
    )).scalar_one() > 0


def _numbers(numbers: list[str]) -> str:
    return ", ".join(f"№{n}" for n in sorted(numbers, key=natural_key))


async def hatch_completion_error(db: AsyncSession, inspection: Inspection) -> str | None:
    """Причина, по которой владелец не может завершить обход, или None.

    Площадка без люков (перечень от округа ещё не загружен) — гейта нет
    вообще, поведение завершения обхода не меняется."""
    hatches = (await db.execute(
        select(Hatch).where(Hatch.site_id == inspection.site_id, Hatch.is_active.is_(True))
    )).scalars().all()
    if not hatches:
        return None

    checked_ids = set((await db.execute(
        select(HatchCheck.hatch_id).where(HatchCheck.inspection_id == inspection.id)
    )).scalars().all())
    missing = [h.number for h in hatches if h.id not in checked_ids]
    if missing:
        return ("Отметьте люк " if len(missing) == 1 else "Отметьте люки: ") + _numbers(missing)

    photo_count = (
        select(func.count()).select_from(Photo)
        .where(Photo.issue_id == HatchCheck.issue_id, Photo.target_type == "issue")
        .correlate(HatchCheck).scalar_subquery()
    )
    without_photo = (await db.execute(
        select(Hatch.number)
        .join(HatchCheck, HatchCheck.hatch_id == Hatch.id)
        .where(
            HatchCheck.inspection_id == inspection.id,
            HatchCheck.state != "ok",
            (HatchCheck.issue_id.is_(None)) | (photo_count == 0),
        )
    )).scalars().all()
    if without_photo:
        prefix = "Нужно фото для люка " if len(without_photo) == 1 else "Нужно фото для люков "
        return prefix + _numbers(list(without_photo))
    return None
