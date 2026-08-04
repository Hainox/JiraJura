"""Reports router."""
import io
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.database import get_db
from app.models import (
    District, Courtyard, Site, Inspection, Issue, ChecklistAnswer, User,
)
from app.schemas import ReportWeeklyOut, ReportMonthlyOut
from app.services.permissions import require_role

router = APIRouter()


@router.get("/weekly", response_model=list[ReportWeeklyOut])
async def weekly_report(
    district_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    week_ago = datetime.utcnow() - timedelta(days=7)
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
):
    month_ago = datetime.utcnow() - timedelta(days=30)
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


# ── Выгрузка в Excel ─────────────────────────────────────────────

INSPECTION_STATUS_RU = {
    "planned": "Запланирован", "in_progress": "В процессе",
    "completed": "Завершён", "issues_found": "Есть нарушения",
    "critical": "Критический",
}
ISSUE_STATUS_RU = {
    "open": "Открыто", "assigned": "Назначено", "in_work": "В работе",
    "fixed": "Устранено", "control": "На контроле", "closed": "Закрыто",
    "overdue": "Просрочено",
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

    if current_user.role == "reviewer" and current_user.district_id is not None:
        district_id = str(current_user.district_id)

    dt_from = datetime.combine(date_from, datetime.min.time()) if date_from else None
    dt_to = (datetime.combine(date_to, datetime.min.time()) + timedelta(days=1)) if date_to else None

    def period(q, column):
        if dt_from is not None:
            q = q.where(column >= dt_from)
        if dt_to is not None:
            q = q.where(column < dt_to)
        return q

    # ── Обходы ──
    insp_q = (
        select(Inspection, District.name, Courtyard.name, Site.type, User.full_name)
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

    insp_data = []
    for insp, dist_name, court_name, site_type, inspector_name in inspections:
        ok_cnt, defect_cnt = answers.get(insp.id, (0, 0))
        insp_data.append((
            _fmt_dt(insp.created_at), dist_name, court_name, site_type,
            inspector_name, INSPECTION_STATUS_RU.get(insp.status, insp.status),
            _fmt_dt(insp.started_at), _fmt_dt(insp.completed_at),
            ok_cnt, defect_cnt, insp.comment or "",
        ))

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

    # ── Сборка файла ──
    wb = Workbook()
    wb.remove(wb.active)  # пустой дефолтный лист

    _sheet(
        wb, "Сводка по районам",
        ["Район", "Всего площадок", "Обходов за период", "Замечаний создано",
         "Закрыто", "Открыто сейчас", "Просрочено"],
        summary_data, [24, 15, 17, 17, 10, 14, 12],
    )
    _sheet(
        wb, "Обходы",
        ["Дата", "Район", "Двор", "Тип площадки", "Инспектор", "Статус",
         "Начат", "Завершён", "Пунктов в порядке", "Дефектов", "Комментарий"],
        insp_data, [16, 20, 40, 20, 24, 16, 16, 16, 16, 10, 40],
    )
    _sheet(
        wb, "Замечания",
        ["Дата", "Район", "Двор", "Заголовок", "Описание", "Критичность",
         "Статус", "Автор", "Назначено", "Срок", "Устранено"],
        iss_data, [16, 20, 40, 30, 40, 12, 12, 24, 24, 16, 16],
    )

    buf = io.BytesIO()
    wb.save(buf)

    stamp = datetime.utcnow().strftime("%Y-%m-%d")
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="journal_export_{stamp}.xlsx"'},
    )
