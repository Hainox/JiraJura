"""Reports router."""
import io
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.database import get_db
from app.models import (
    District, Courtyard, Site, Inspection, Issue, ChecklistAnswer, ChecklistItem, User, UserInvite,
)
from app.schemas import ReportWeeklyOut, ReportMonthlyOut, DashboardDistrictRow, DashboardOut
from app.services.permissions import require_role
from app.services.timezone import MSK, msk_day_bounds_utc

router = APIRouter()

# Обход считается завершённым, даже если по итогу нашлись нарушения —
# 'issues_found'/'critical' это тоже финальные статусы (проставляются вместе
# с completed_at, см. update_inspection в inspections.py), а не промежуточные
# наравне с 'in_progress'. Без этого списка "Завершено" в дашборде/отчётах
# занижался, а "В процессе" — по факту не завышался, но обходы с найденными
# нарушениями просто выпадали из обеих колонок.
INSPECTION_DONE_STATUSES = ("completed", "issues_found", "critical")


@router.get("/weekly", response_model=list[ReportWeeklyOut])
async def weekly_report(
    district_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("reviewer", "admin")),
):
    if current_user.role == "reviewer" and current_user.district_id is not None:
        district_id = str(current_user.district_id)

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    results = []

    dist_q = select(District).order_by(District.name)
    if district_id:
        dist_q = dist_q.where(District.id == district_id)
    districts = (await db.execute(dist_q)).scalars().all()

    for d in districts:
        court_ids = (
            await db.execute(select(Courtyard.id).where(Courtyard.district_id == d.id))
        ).scalars().all()
        court_ids = [str(c) for c in court_ids]

        total_sites = (await db.execute(
            select(func.count()).select_from(Site).where(
                Site.courtyard_id.in_(court_ids), Site.is_active
            )
        )).scalar_one() or 0

        inspected = (await db.execute(
            select(func.count()).select_from(Inspection).where(
                Inspection.site_id.in_(
                    select(Site.id).where(Site.courtyard_id.in_(court_ids))
                ),
                Inspection.created_at >= week_ago,
            )
        )).scalar_one() or 0

        issues_open = (await db.execute(
            select(func.count()).select_from(Issue).where(
                Issue.site_id.in_(
                    select(Site.id).where(Site.courtyard_id.in_(court_ids))
                ),
                Issue.status.in_(["open", "assigned", "in_work"]),
            )
        )).scalar_one() or 0

        issues_overdue = (await db.execute(
            select(func.count()).select_from(Issue).where(
                Issue.site_id.in_(
                    select(Site.id).where(Site.courtyard_id.in_(court_ids))
                ),
                Issue.status == "overdue",
            )
        )).scalar_one() or 0

        results.append(ReportWeeklyOut(
            district_id=d.id,
            district_name=d.name,
            total_sites=total_sites,
            inspected_sites=inspected,
            issues_open=issues_open,
            issues_overdue=issues_overdue,
        ))

    return results


@router.get("/monthly", response_model=list[ReportMonthlyOut])
async def monthly_report(
    district_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("reviewer", "admin")),
):
    if current_user.role == "reviewer" and current_user.district_id is not None:
        district_id = str(current_user.district_id)

    month_ago = datetime.now(timezone.utc) - timedelta(days=30)
    results = []

    dist_q = select(District).order_by(District.name)
    if district_id:
        dist_q = dist_q.where(District.id == district_id)
    districts = (await db.execute(dist_q)).scalars().all()

    for d in districts:
        court_ids = (
            await db.execute(select(Courtyard.id).where(Courtyard.district_id == d.id))
        ).scalars().all()
        court_ids = [str(c) for c in court_ids]

        site_sub = select(Site.id).where(Site.courtyard_id.in_(court_ids))

        total_sites = (await db.execute(
            select(func.count()).select_from(Site).where(Site.courtyard_id.in_(court_ids), Site.is_active)
        )).scalar_one() or 0

        inspected = (await db.execute(
            select(func.count()).select_from(Inspection).where(
                Inspection.site_id.in_(site_sub),
                Inspection.created_at >= month_ago,
            )
        )).scalar_one() or 0

        created = (await db.execute(
            select(func.count()).select_from(Issue).where(
                Issue.site_id.in_(site_sub), Issue.created_at >= month_ago
            )
        )).scalar_one() or 0

        closed = (await db.execute(
            select(func.count()).select_from(Issue).where(
                Issue.site_id.in_(site_sub), Issue.status == "closed",
                Issue.updated_at >= month_ago,
            )
        )).scalar_one() or 0

        overdue = (await db.execute(
            select(func.count()).select_from(Issue).where(
                Issue.site_id.in_(site_sub), Issue.status == "overdue"
            )
        )).scalar_one() or 0

        results.append(ReportMonthlyOut(
            district_id=d.id,
            district_name=d.name,
            total_sites=total_sites,
            inspected_sites=inspected,
            issues_created=created,
            issues_closed=closed,
            issues_overdue=overdue,
        ))

    return results


# ── Дашборд админа ─────────────────────────────────────────────

@router.get("/dashboard", response_model=DashboardOut)
async def admin_dashboard(
    district_id: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("reviewer", "admin")),
):
    """Сводка по районам для дашборда: обходы, замечания, статусы."""
    if current_user.role == "reviewer" and current_user.district_id is not None:
        district_id = str(current_user.district_id)

    dt_from, dt_to = msk_day_bounds_utc(date_from, date_to)

    def period(q, column):
        if dt_from is not None:
            q = q.where(column >= dt_from)
        if dt_to is not None:
            q = q.where(column < dt_to)
        return q

    dist_q = select(District).order_by(District.name)
    if district_id:
        dist_q = dist_q.where(District.id == district_id)
    districts = (await db.execute(dist_q)).scalars().all()

    rows: list[DashboardDistrictRow] = []
    total_row = DashboardDistrictRow(
        district_id=UUID("00000000-0000-0000-0000-000000000000"),
        district_name="ВСЕГО", total_sites=0, inspections_total=0,
        inspections_completed=0, inspections_in_progress=0,
        checklist_defects=0,
        issues_total=0, issues_open=0, issues_fixed=0,
        issues_revision_needed=0, issues_closed=0,
    )

    for d in districts:
        site_sub = (
            select(Site.id)
            .join(Courtyard, Site.courtyard_id == Courtyard.id)
            .where(Courtyard.district_id == d.id)
        )

        total_sites = (await db.execute(
            select(func.count()).select_from(Site).where(Site.id.in_(site_sub), Site.is_active)
        )).scalar_one() or 0

        insp_base = select(func.count()).select_from(Inspection).where(Inspection.site_id.in_(site_sub))
        inspections_total = (await db.execute(period(insp_base, Inspection.created_at))).scalar_one() or 0
        inspections_completed = (await db.execute(period(
            select(func.count()).select_from(Inspection).where(Inspection.site_id.in_(site_sub), Inspection.status.in_(INSPECTION_DONE_STATUSES)),
            Inspection.created_at,
        ))).scalar_one() or 0
        inspections_in_progress = (await db.execute(period(
            select(func.count()).select_from(Inspection).where(Inspection.site_id.in_(site_sub), Inspection.status == "in_progress"),
            Inspection.created_at,
        ))).scalar_one() or 0

        # Реально выявлено при обходе — по чек-листу, независимо от того,
        # оформил ли инспектор отдельное замечание (см. комментарий у поля
        # в schemas.py). Именно это число надо использовать для оценки
        # района, а не issues_total ниже.
        defects_base = (
            select(func.count()).select_from(ChecklistAnswer)
            .join(Inspection, ChecklistAnswer.inspection_id == Inspection.id)
            .where(Inspection.site_id.in_(site_sub), ChecklistAnswer.result == "defect")
        )
        checklist_defects = (await db.execute(period(defects_base, ChecklistAnswer.created_at))).scalar_one() or 0

        iss_base = select(func.count()).select_from(Issue).where(Issue.site_id.in_(site_sub))
        issues_total = (await db.execute(period(iss_base, Issue.created_at))).scalar_one() or 0
        issues_open = (await db.execute(period(
            select(func.count()).select_from(Issue).where(
                Issue.site_id.in_(site_sub), Issue.status.in_(["open", "assigned", "in_work"])
            ), Issue.created_at,
        ))).scalar_one() or 0
        issues_fixed = (await db.execute(period(
            select(func.count()).select_from(Issue).where(Issue.site_id.in_(site_sub), Issue.status == "fixed"),
            Issue.created_at,
        ))).scalar_one() or 0
        issues_revision_needed = (await db.execute(period(
            select(func.count()).select_from(Issue).where(Issue.site_id.in_(site_sub), Issue.status == "revision_needed"),
            Issue.created_at,
        ))).scalar_one() or 0
        issues_closed = (await db.execute(period(
            select(func.count()).select_from(Issue).where(Issue.site_id.in_(site_sub), Issue.status == "closed"),
            Issue.created_at,
        ))).scalar_one() or 0

        row = DashboardDistrictRow(
            district_id=d.id, district_name=d.name, total_sites=total_sites,
            inspections_total=inspections_total, inspections_completed=inspections_completed,
            inspections_in_progress=inspections_in_progress,
            checklist_defects=checklist_defects,
            issues_total=issues_total, issues_open=issues_open,
            issues_fixed=issues_fixed, issues_revision_needed=issues_revision_needed,
            issues_closed=issues_closed,
        )
        rows.append(row)

        # суммируем в totals
        total_row.total_sites += total_sites
        total_row.inspections_total += inspections_total
        total_row.inspections_completed += inspections_completed
        total_row.inspections_in_progress += inspections_in_progress
        total_row.checklist_defects += checklist_defects
        total_row.issues_total += issues_total
        total_row.issues_open += issues_open
        total_row.issues_fixed += issues_fixed
        total_row.issues_revision_needed += issues_revision_needed
        total_row.issues_closed += issues_closed

    return DashboardOut(districts=rows, totals=total_row)


# ── Выгрузка в Excel ─────────────────────────────────────────────

INSPECTION_STATUS_RU = {
    "planned": "Запланирован", "in_progress": "В процессе",
    "completed": "Завершён", "issues_found": "Есть нарушения",
    "critical": "Критический",
}
ISSUE_STATUS_RU = {
    "open": "Открыто", "assigned": "Назначено", "in_work": "В работе",
    "fixed": "Устранено", "control": "На контроле", "closed": "Закрыто",
    "overdue": "Просрочено", "revision_needed": "На доработке",
}
CRITICALITY_RU = {
    "low": "Низкая", "medium": "Средняя", "high": "Высокая",
    "critical": "Критическая",
}


def _fmt_dt(value) -> str:
    return value.strftime("%d.%m.%Y %H:%M") if value else ""


def _sheet(wb, title: str, headers: list[str], rows: list[tuple], widths: list[int]):
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    ws = wb.create_sheet(title)
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append(row)
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    return ws


@router.get("/export.xlsx")
async def export_xlsx(
    district_id: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("reviewer", "admin")),
):
    """Выгрузка журнала в Excel: сводка по районам, обходы, замечания.

    reviewer с заданным district_id видит только свой район — параметр
    district_id для него принудительно замещается собственным районом.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.chart import BarChart, PieChart, Reference
    from openpyxl.chart.label import DataLabelList

    if current_user.role == "reviewer" and current_user.district_id is not None:
        district_id = str(current_user.district_id)

    dt_from, dt_to = msk_day_bounds_utc(date_from, date_to)

    def period(q, column):
        if dt_from is not None:
            q = q.where(column >= dt_from)
        if dt_to is not None:
            q = q.where(column < dt_to)
        return q

    # ── Регистрация (для листов "Обзор"/"Регистрация" — тот же расчёт, что
    # в эталонном generate_summary_report.py, который раньше запускался
    # только вручную на сервере; переносим сюда, чтобы админ/reviewer могли
    # получить тот же отчёт кнопкой "Excel" в приложении, без SSH) ──
    pending_q = select(UserInvite.district_id, UserInvite.full_name, UserInvite.role, UserInvite.created_at).where(UserInvite.used_at.is_(None))
    if district_id:
        pending_q = pending_q.where(UserInvite.district_id == district_id)
    pending_q = pending_q.order_by(UserInvite.full_name, UserInvite.created_at.desc())
    pending_rows = (await db.execute(pending_q)).all()

    # Дедуп по ФИО в рамках каждой группы (район/админы/окружные) — один
    # человек мог быть приглашён повторно под другим логином (опечатка).
    def _dedup_by_name(rows):
        seen, out = set(), []
        for r in rows:
            if r.full_name in seen:
                continue
            seen.add(r.full_name)
            out.append(r)
        return out

    pending_by_district_raw: dict = {}
    pending_admins_raw, pending_okrug_reviewers_raw = [], []
    for r in pending_rows:
        if r.role == "admin":
            pending_admins_raw.append(r)
        elif r.district_id is None:
            pending_okrug_reviewers_raw.append(r)
        else:
            pending_by_district_raw.setdefault(r.district_id, []).append(r)
    pending_admins = _dedup_by_name(pending_admins_raw)
    pending_okrug_reviewers = _dedup_by_name(pending_okrug_reviewers_raw)
    pending_by_district = {did: _dedup_by_name(rows) for did, rows in pending_by_district_raw.items()}

    reg_districts_q = select(District).order_by(District.name)
    if district_id:
        reg_districts_q = reg_districts_q.where(District.id == district_id)
    reg_districts = (await db.execute(reg_districts_q)).scalars().all()

    reg_stats = []
    for d in reg_districts:
        registered = (await db.execute(
            select(func.count()).select_from(User).where(User.district_id == d.id, User.is_active)
        )).scalar_one()
        pending = pending_by_district.get(d.id, [])
        total = registered + len(pending)
        pct = (registered / total) if total else 1.0
        reg_stats.append({"name": d.name, "registered": registered, "pending": pending, "total": total, "pct": pct})
    reg_stats.sort(key=lambda x: x["pct"])
    total_reg = sum(x["registered"] for x in reg_stats)
    total_all_invited = sum(x["total"] for x in reg_stats)
    overall_reg_pct = (total_reg / total_all_invited) if total_all_invited else 1.0

    # ── Топ категорий нарушений и лидеры дня — та же зона видимости
    # (district_id), что и у остальных листов этой выгрузки ──
    # cat_expr переиспользуется как единый объект и в SELECT, и в GROUP BY —
    # если вместо этого написать func.coalesce(...) дважды, SQLAlchemy
    # биндит каждое вхождение отдельным параметром, и Postgres не признаёт
    # их одним и тем же выражением (GroupingError: must appear in GROUP BY).
    cat_expr = func.coalesce(ChecklistItem.category, "Без категории").label("cat")
    top_cat_q = (
        select(cat_expr, func.count())
        .select_from(ChecklistAnswer)
        .join(ChecklistItem, ChecklistAnswer.checklist_item_id == ChecklistItem.id)
        .where(ChecklistAnswer.result == "defect")
    )
    if district_id:
        top_cat_q = (
            top_cat_q.join(Inspection, ChecklistAnswer.inspection_id == Inspection.id)
            .join(Site, Inspection.site_id == Site.id).join(Courtyard, Site.courtyard_id == Courtyard.id)
            .where(Courtyard.district_id == district_id)
        )
    top_cat_q = top_cat_q.group_by(cat_expr).order_by(func.count().desc()).limit(5)
    top_categories = (await db.execute(top_cat_q)).all()

    odd_districts = [d.name for d in (await db.execute(select(District))).scalars().all() if ";" in d.name or "," in d.name]

    today_msk = datetime.now(MSK).date()
    leaders_q = (
        select(User.id, User.full_name, func.count())
        .select_from(Inspection).join(User, Inspection.inspector_id == User.id)
        .where(func.date(func.timezone("Europe/Moscow", Inspection.created_at)) == today_msk)
    )
    if district_id:
        leaders_q = leaders_q.join(Site, Inspection.site_id == Site.id).join(Courtyard, Site.courtyard_id == Courtyard.id).where(Courtyard.district_id == district_id)
    leaders_q = leaders_q.group_by(User.id, User.full_name).order_by(func.count().desc()).limit(5)
    leaders_today = (await db.execute(leaders_q)).all()

    # ── Обходы ──
    insp_q = (
        select(Inspection, District.name, Courtyard.name, Site.type, User.full_name, User.phone)
        .join(Site, Inspection.site_id == Site.id)
        .join(Courtyard, Site.courtyard_id == Courtyard.id)
        .join(District, Courtyard.district_id == District.id)
        .join(User, Inspection.inspector_id == User.id)
        .order_by(Inspection.created_at.desc())
    )
    if district_id:
        insp_q = insp_q.where(District.id == district_id)
    insp_q = period(insp_q, Inspection.created_at)
    inspections = (await db.execute(insp_q)).all()

    ans_rows = (await db.execute(
        select(
            ChecklistAnswer.inspection_id,
            func.count().filter(ChecklistAnswer.result == "ok"),
            func.count().filter(ChecklistAnswer.result == "defect"),
        ).group_by(ChecklistAnswer.inspection_id)
    )).all()
    answers = {row[0]: (row[1], row[2]) for row in ans_rows}

    # Считаем фото на каждый обход
    from app.models import Photo
    photo_counts = {}
    photo_rows = (await db.execute(
        select(Photo.inspection_id, func.count())
        .where(Photo.target_type.in_(["inspection", "checklist_answer"]))
        .group_by(Photo.inspection_id)
    )).all()
    for insp_id, cnt in photo_rows:
        photo_counts[str(insp_id)] = cnt

    insp_data = []
    for insp, dist_name, court_name, site_type, inspector_name, phone in inspections:
        ok_cnt, defect_cnt = answers.get(insp.id, (0, 0))
        insp_data.append((
            _fmt_dt(insp.created_at), dist_name, court_name, site_type,
            inspector_name, phone or "",
            INSPECTION_STATUS_RU.get(insp.status, insp.status),
            _fmt_dt(insp.started_at), _fmt_dt(insp.completed_at),
            ok_cnt, defect_cnt, photo_counts.get(str(insp.id), 0),
            insp.comment or "",
        ))

    # ── Задания (снимок "сейчас", а не журнал за период) ──
    # Проверяющие просили именно это отдельно от "Обходы" выше: та вкладка —
    # хронологический лог за выбранный период, а тут — по каждой активной
    # площадке в зоне видимости: кто за неё отвечает и когда там были в
    # последний раз (независимо от периода отчёта), чтобы сразу видеть, где
    # давно не было обхода или он вообще не назначен. district_id/scope тот
    # же, что и у остальных листов этой выгрузки — период (dt_from/dt_to)
    # тут намеренно не применяется, это не история, а текущее состояние.
    assign_q = (
        select(Site, Courtyard.name, District.name, User.full_name, User.phone)
        .join(Courtyard, Site.courtyard_id == Courtyard.id)
        .join(District, Courtyard.district_id == District.id)
        .outerjoin(User, Site.assigned_inspector_id == User.id)
        .where(Site.is_active)
    )
    if district_id:
        assign_q = assign_q.where(District.id == district_id)
    site_rows = (await db.execute(assign_q)).all()

    site_ids = [site.id for site, *_ in site_rows]
    last_by_site: dict = {}
    if site_ids:
        last_sub = (
            select(Inspection.site_id, func.max(Inspection.created_at).label("last_dt"))
            .where(Inspection.site_id.in_(site_ids))
            .group_by(Inspection.site_id)
            .subquery()
        )
        last_rows = (await db.execute(
            select(Inspection.site_id, Inspection.created_at, Inspection.status)
            .join(last_sub, (Inspection.site_id == last_sub.c.site_id) & (Inspection.created_at == last_sub.c.last_dt))
        )).all()
        last_by_site = {row.site_id: (row.created_at, row.status) for row in last_rows}

    assignment_rows = []
    for site, court_name, dist_name, insp_name, insp_phone in site_rows:
        last = last_by_site.get(site.id)
        assignment_rows.append((
            last[0] if last else None,  # ключ сортировки, вырежем перед записью в лист
            dist_name, court_name, site.type,
            insp_name or "Не назначена", insp_phone or "",
            _fmt_dt(last[0]) if last else "Обхода ещё не было",
            INSPECTION_STATUS_RU.get(last[1], last[1]) if last else "",
        ))
    # Сначала то, что реально требует внимания: без единого обхода — выше
    # всего, дальше по возрастанию давности последнего визита.
    assignment_rows.sort(key=lambda r: (r[0] is not None, r[0]))
    assignment_data = [row[1:] for row in assignment_rows]

    # ── Замечания ──
    Assignee = aliased(User)
    iss_q = (
        select(Issue, District.name, Courtyard.name, User.full_name, Assignee.full_name)
        .join(Site, Issue.site_id == Site.id)
        .join(Courtyard, Site.courtyard_id == Courtyard.id)
        .join(District, Courtyard.district_id == District.id)
        .join(User, Issue.created_by == User.id)
        .outerjoin(Assignee, Issue.assigned_to == Assignee.id)
        .order_by(Issue.created_at.desc())
    )
    if district_id:
        iss_q = iss_q.where(District.id == district_id)
    iss_q = period(iss_q, Issue.created_at)
    issues = (await db.execute(iss_q)).all()

    iss_data = [
        (
            _fmt_dt(iss.created_at), dist_name, court_name, iss.title,
            iss.description or "", CRITICALITY_RU.get(iss.criticality, iss.criticality),
            ISSUE_STATUS_RU.get(iss.status, iss.status), author_name,
            assignee_name or "", _fmt_dt(iss.due_date), _fmt_dt(iss.fixed_at),
        )
        for iss, dist_name, court_name, author_name, assignee_name in issues
    ]

    # ── Нарушения по чек-листу (детально) ──
    defect_q = (
        select(
            ChecklistAnswer, ChecklistItem.question, ChecklistItem.category,
            Inspection.created_at, District.name, Courtyard.name,
            Site.type, User.full_name,
        )
        .join(Inspection, ChecklistAnswer.inspection_id == Inspection.id)
        .join(ChecklistItem, ChecklistAnswer.checklist_item_id == ChecklistItem.id)
        .join(Site, Inspection.site_id == Site.id)
        .join(Courtyard, Site.courtyard_id == Courtyard.id)
        .join(District, Courtyard.district_id == District.id)
        .join(User, Inspection.inspector_id == User.id)
        .where(ChecklistAnswer.result == "defect")
        .order_by(District.name, Inspection.created_at.desc())
    )
    if district_id:
        defect_q = defect_q.where(District.id == district_id)
    defect_q = period(defect_q, Inspection.created_at)
    defects = (await db.execute(defect_q)).all()

    defect_data = [
        (
            _fmt_dt(insp_dt), dist_name, court_name, site_type,
            category or "", question, answer.comment or "",
            inspector_name,
        )
        for answer, question, category, insp_dt, dist_name, court_name, site_type, inspector_name in defects
    ]

    # ── Сводка по районам ──
    dist_q = select(District).order_by(District.name)
    if district_id:
        dist_q = dist_q.where(District.id == district_id)
    districts = (await db.execute(dist_q)).scalars().all()

    summary_data = []
    for d in districts:
        site_sub = (
            select(Site.id)
            .join(Courtyard, Site.courtyard_id == Courtyard.id)
            .where(Courtyard.district_id == d.id)
        )
        total_sites = (await db.execute(
            select(func.count()).select_from(Site).where(
                Site.id.in_(site_sub), Site.is_active
            )
        )).scalar_one() or 0
        inspected = (await db.execute(period(
            select(func.count()).select_from(Inspection).where(Inspection.site_id.in_(site_sub)),
            Inspection.created_at,
        ))).scalar_one() or 0
        created = (await db.execute(period(
            select(func.count()).select_from(Issue).where(Issue.site_id.in_(site_sub)),
            Issue.created_at,
        ))).scalar_one() or 0
        closed = (await db.execute(period(
            select(func.count()).select_from(Issue).where(
                Issue.site_id.in_(site_sub), Issue.status == "closed"
            ),
            Issue.created_at,
        ))).scalar_one() or 0
        open_now = (await db.execute(
            select(func.count()).select_from(Issue).where(
                Issue.site_id.in_(site_sub),
                Issue.status.in_(["open", "assigned", "in_work"]),
            )
        )).scalar_one() or 0
        overdue = (await db.execute(
            select(func.count()).select_from(Issue).where(
                Issue.site_id.in_(site_sub), Issue.status == "overdue"
            )
        )).scalar_one() or 0
        summary_data.append((d.name, total_sites, inspected, created, closed, open_now, overdue))

    # ── Динамика по дням (инспектор × дата) ──
    # Группируем по User.id, а не по ФИО — у full_name нет уникальности в
    # базе, и два инспектора-тёзки схлопывались бы в один столбец с суммой
    # их обходов на двоих.
    from collections import defaultdict
    day_stats_q = (
        select(
            func.date(Inspection.created_at), User.id, User.full_name, func.count()
        )
        .join(User, Inspection.inspector_id == User.id)
        .group_by(func.date(Inspection.created_at), User.id, User.full_name)
        .order_by(func.date(Inspection.created_at).desc(), User.full_name)
    )
    if district_id:
        day_stats_q = day_stats_q.join(Site).join(Courtyard).where(Courtyard.district_id == district_id)
    day_stats_q = period(day_stats_q, Inspection.created_at)
    day_stats = (await db.execute(day_stats_q)).all()

    # группируем: дата → {id инспектора: кол-во}
    day_data: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    inspector_names: dict = {}
    for dt, insp_id, name, cnt in day_stats:
        day_data[str(dt)][insp_id] = cnt
        inspector_names[insp_id] = name
    sorted_inspector_ids = sorted(inspector_names, key=lambda i: (inspector_names[i], str(i)))
    sorted_inspectors = [inspector_names[i] for i in sorted_inspector_ids]
    dynamics_rows = []
    for dt in sorted(day_data.keys(), reverse=True):
        row = [dt] + [day_data[dt].get(insp_id, 0) for insp_id in sorted_inspector_ids]
        dynamics_rows.append(tuple(row))

    # ── Просроченные замечания ──
    overdue_q = (
        select(Issue, District.name, Courtyard.name, User.full_name)
        .join(Site, Issue.site_id == Site.id)
        .join(Courtyard, Site.courtyard_id == Courtyard.id)
        .join(District, Courtyard.district_id == District.id)
        .join(User, Issue.created_by == User.id)
        .where(Issue.status == "overdue")
        .order_by(Issue.due_date)
    )
    if district_id:
        overdue_q = overdue_q.where(District.id == district_id)
    overdue_items = (await db.execute(overdue_q)).all()
    overdue_rows = [
        (iss.title, dist_name, court_name, author_name,
         _fmt_dt(iss.created_at), _fmt_dt(iss.due_date), iss.description or "")
        for iss, dist_name, court_name, author_name in overdue_items
    ]

    # ── Сборка файла ──
    wb = Workbook()

    RED = PatternFill("solid", fgColor="FFC7CE")
    YELLOW = PatternFill("solid", fgColor="FFEB9C")
    GREEN = PatternFill("solid", fgColor="C6EFCE")

    def _pie(ws, title, cats_ref, data_ref, anchor):
        chart = PieChart()
        chart.title = title
        chart.height, chart.width = 7, 10
        chart.add_data(data_ref, titles_from_data=False)
        chart.set_categories(cats_ref)
        chart.dataLabels = DataLabelList()
        chart.dataLabels.showVal = True
        chart.dataLabels.showPercent = True
        ws.add_chart(chart, anchor)

    def _bar(ws, title, cats_ref, data_ref, anchor, y_title=""):
        chart = BarChart()
        chart.type = "col"
        chart.title = title
        chart.y_axis.title = y_title
        chart.height, chart.width = 9, 18
        chart.add_data(data_ref, titles_from_data=True)
        chart.set_categories(cats_ref)
        ws.add_chart(chart, anchor)

    # ── Обзор — тот же лист, что в generate_summary_report.py (раньше
    # доступен только через ручной запуск скрипта на сервере) ──
    now_str = datetime.now(MSK).strftime("%d.%m.%Y %H:%M")
    total_sites_all = sum(x[1] for x in summary_data) if summary_data else 0
    total_insp_all = len(insp_data)
    total_insp_done_all = sum(1 for r in insp_data if r[6] != "В процессе")
    total_iss_all = len(iss_data)
    total_iss_closed_all = sum(1 for r in iss_data if r[6] == "Закрыто")

    ov = wb.active
    ov.title = "Обзор"

    def _row(*vals):
        ov.append(list(vals))

    _row("Сводный отчёт по проекту «Журнал обхода площадок» — САО г. Москвы")
    ov["A1"].font = Font(bold=True, size=14)
    _row(f"Снимок на {now_str} (МСК)")
    _row()
    _row("Ключевые цифры")
    ov[f"A{ov.max_row}"].font = Font(bold=True)
    _row("Регистрация", f"{total_reg} / {total_all_invited} ({overall_reg_pct:.0%})")
    _row("Площадок в системе", total_sites_all)
    _row("Обходов всего / завершено", f"{total_insp_all} / {total_insp_done_all} (в процессе: {total_insp_all - total_insp_done_all})")
    _row("Нарушений создано / открыто сейчас", f"{total_iss_all} / {total_iss_all - total_iss_closed_all} (закрыто: {total_iss_closed_all})")
    _row()
    _row("Требуют внимания в первую очередь")
    ov[f"A{ov.max_row}"].font = Font(bold=True)

    low_reg = [x for x in reg_stats if x["pct"] < 0.5 and x["total"] > 0]
    if low_reg:
        names = ", ".join(f"{x['name']} ({x['pct']:.0%})" for x in low_reg)
        _row(f"• Регистрация < 50%: {names} — стоит выяснить, не мешает ли что-то войти в систему.")

    not_registered_admins = pending_admins + pending_okrug_reviewers
    if not_registered_admins:
        names = ", ".join(r.full_name for r in not_registered_admins)
        _row(f"• Не зарегистрированы админы/окружные проверяющие ({len(not_registered_admins)}): {names} — у них административные права, стоит дожать в первую очередь.")

    if top_categories:
        cats = ", ".join(f"{cat} ({cnt})" for cat, cnt in top_categories)
        _row(f"• Систематические типы нарушений: {cats}.")

    if odd_districts:
        _row(f"• Похоже на опечатку/задвоение района при заведении в систему: {', '.join(odd_districts)} — не отдельный реальный район.")

    _row()
    _row("Лидеры дня по личной активности (обходов начато сегодня)")
    ov[f"A{ov.max_row}"].font = Font(bold=True)
    for _id, full_name, cnt in leaders_today:
        _row(f"   {full_name}", cnt)

    _row()
    _row("Состав отчёта")
    ov[f"A{ov.max_row}"].font = Font(bold=True)
    for name, desc in [
        ("Регистрация", "Кто зарегистрирован/нет по районам, поимённо, худшие районы сверху"),
        ("Задания", "Снимок сейчас: кто отвечает за площадку и когда там были в последний раз"),
        ("Сводка по районам", "Площадки/обходы/нарушения за период, в одной таблице"),
        ("Обходы", "Детальный лог всех обходов: инспектор, площадка, статус, ОК/дефектов/фото"),
        ("Нарушения по чек-листу", "Разбивка нарушений по категориям и конкретным пунктам чек-листа"),
        ("Замечания", "Все зафиксированные замечания с критичностью и статусом"),
        ("Просроченные замечания", "Замечания с истёкшим сроком устранения"),
        ("Динамика", "Активность каждого сотрудника по дням (число отмеченных пунктов чек-листа)"),
    ]:
        _row(name, desc)

    for col, w in zip("ABCDEF", (55, 30, 20, 15, 15, 15)):
        ov.column_dimensions[col].width = w

    ov["H1"] = "Обходы"
    ov["H2"], ov["I2"] = "Завершено", total_insp_done_all
    ov["H3"], ov["I3"] = "В процессе", total_insp_all - total_insp_done_all
    ov["H5"] = "Замечания"
    ov["H6"], ov["I6"] = "Открыто", total_iss_all - total_iss_closed_all
    ov["H7"], ov["I7"] = "Закрыто", total_iss_closed_all
    if total_insp_all > 0:
        _pie(ov, "Обходы: завершено / в процессе",
             Reference(ov, min_col=8, min_row=2, max_row=3), Reference(ov, min_col=9, min_row=2, max_row=3), "K2")
    if total_iss_all > 0:
        _pie(ov, "Замечания: открыто / закрыто",
             Reference(ov, min_col=8, min_row=6, max_row=7), Reference(ov, min_col=9, min_row=6, max_row=7), "K16")

    # ── Регистрация ──
    reg_ws = wb.create_sheet("Регистрация")
    reg_ws.append(["Регистрация пользователей по районам"])
    reg_ws.append([f"Снимок на {now_str} — user_invites + users, дедуп по ФИО"])
    reg_ws.append([])
    reg_ws.append(["Район", "Зарегистрировано", "Всего приглашено", "% регистрации"])
    for cell in reg_ws[reg_ws.max_row]:
        cell.font = Font(bold=True)
    for x in reg_stats:
        reg_ws.append([x["name"], x["registered"], x["total"], x["pct"]])
        fill = RED if x["pct"] < 0.5 else (YELLOW if x["pct"] < 0.8 else GREEN)
        reg_ws.cell(reg_ws.max_row, 4).fill = fill
        reg_ws.cell(reg_ws.max_row, 4).number_format = "0%"
    reg_ws.append(["ИТОГО", total_reg, total_all_invited, overall_reg_pct])
    for cell in reg_ws[reg_ws.max_row]:
        cell.font = Font(bold=True)
    reg_ws.cell(reg_ws.max_row, 4).number_format = "0%"

    reg_ws.append([])
    reg_ws.append(["Не зарегистрированы поимённо (по районам, худшие сверху)"])
    reg_ws[f"A{reg_ws.max_row}"].font = Font(bold=True)
    for x in reg_stats:
        if not x["pending"]:
            continue
        reg_ws.append([x["name"]])
        reg_ws[f"A{reg_ws.max_row}"].font = Font(bold=True)
        for r in x["pending"]:
            reg_ws.append([f"   {r.full_name}"])

    if not district_id and pending_okrug_reviewers:
        reg_ws.append([])
        reg_ws.append(["Проверяющие без района (весь округ) — не зарегистрированы"])
        reg_ws[f"A{reg_ws.max_row}"].font = Font(bold=True)
        for r in pending_okrug_reviewers:
            reg_ws.append([f"   {r.full_name}"])

    if not district_id and pending_admins:
        reg_ws.append([])
        reg_ws.append(["Админы — не зарегистрированы"])
        reg_ws[f"A{reg_ws.max_row}"].font = Font(bold=True)
        for r in pending_admins:
            reg_ws.append([f"   {r.full_name}"])

    if odd_districts:
        reg_ws.append([])
        reg_ws.append([f"* {', '.join(odd_districts)} — вероятная опечатка/задвоение при заведении района, не отдельный реальный район."])
    reg_ws.append(["Цвет строки: красный < 50% регистрации, жёлтый 50–80%, зелёный ≥ 80%."])
    for col, w in zip("ABCD", (45, 18, 18, 15)):
        reg_ws.column_dimensions[col].width = w

    if reg_stats:
        n = len(reg_stats)
        _bar(reg_ws, "% регистрации по районам",
             Reference(reg_ws, min_col=1, min_row=5, max_row=4 + n),
             Reference(reg_ws, min_col=4, min_row=4, max_row=4 + n), "F5", y_title="%")

    # Первым листом после "Обзор"/"Регистрация" — снимок "кто чем занят
    # прямо сейчас", не история за период: это то, что проверяющему нужно
    # открыть первым делом.
    _sheet(wb, "Задания",
        ["Район", "Двор", "Тип площадки", "Назначенный инспектор", "Телефон", "Последний обход", "Статус последнего обхода"],
        assignment_data, [24, 40, 20, 26, 16, 18, 22])
    _sheet(wb, "Сводка по районам",
        ["Район", "Всего площадок", "Обходов за период", "Замечаний создано", "Закрыто", "Открыто сейчас", "Просрочено"],
        summary_data, [24, 15, 17, 17, 10, 14, 12])
    _sheet(wb, "Обходы",
        ["Дата", "Район", "Двор", "Тип площадки", "Инспектор", "Телефон", "Статус", "Начат", "Завершён", "Пунктов ОК", "Дефектов", "Фото", "Комментарий"],
        insp_data, [16, 20, 40, 20, 24, 16, 14, 16, 16, 12, 10, 7, 40])
    _sheet(wb, "Нарушения по чек-листу",
        ["Дата обхода", "Район", "Двор", "Тип площадки", "Категория", "Пункт чек-листа", "Комментарий инспектора", "Инспектор"],
        defect_data, [16, 20, 40, 20, 18, 50, 40, 24])
    _sheet(wb, "Замечания",
        ["Дата", "Район", "Двор", "Заголовок", "Описание", "Критичность", "Статус", "Автор", "Назначено", "Срок", "Устранено"],
        iss_data, [16, 20, 40, 30, 40, 12, 12, 24, 24, 16, 16])
    _sheet(wb, "Просроченные замечания",
        ["Заголовок", "Район", "Двор", "Автор", "Создано", "Срок", "Описание"],
        overdue_rows, [30, 20, 40, 24, 16, 16, 40])

    if dynamics_rows:
        _sheet(wb, "Динамика",
            ["Дата"] + sorted_inspectors,
            dynamics_rows, [12] + [12] * len(sorted_inspectors))

    buf = io.BytesIO()
    wb.save(buf)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="journal_export_{stamp}.xlsx"'},
    )
