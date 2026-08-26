"""Grouped statistics implementation shared by API and export renderers."""

from datetime import timedelta, timezone, datetime

from sqlalchemy import Date, cast, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ChecklistAnswer, Courtyard, District, Inspection, Issue, IssueCategory,
    IssueStatusHistory, Site,
)
from app.schemas import (
    StatsCategoriesOut, StatsCategoryRow, StatsDashboardOut, StatsDistrictRow,
    StatsDynamicsDay, StatsDynamicsOut, StatsPeriodOut,
)
from app.services.timezone import MSK
from .definitions import DONE_STATUSES, NIL_UUID, ON_CHECK_STATUSES, OVERDUE_STATUSES, percent
from .filters import StatisticsFilter
from .queries import issue_bucket_columns


def _site_type_clause(f: StatisticsFilter):
    """true() — SQL-нейтральный no-op, когда фильтр по типу площадки не
    задан, чтобы можно было включать в .where(...) как обычный аргумент
    без ветвления в каждом запросе (все они уже джойнят Site)."""
    return Site.type == f.site_type if f.site_type else true()


class StatisticsService:
    def __init__(self, db: AsyncSession, filters: StatisticsFilter):
        self.db = db
        self.filters = filters
        self.generated_at = datetime.now(timezone.utc)

    @property
    def _period(self) -> StatsPeriodOut:
        return StatsPeriodOut(date_from=self.filters.date_from, date_to=self.filters.date_to)

    async def dashboard(self) -> StatsDashboardOut:
        f = self.filters
        district_stmt = select(District.id, District.name).order_by(District.name)
        if f.district_id:
            district_stmt = district_stmt.where(District.id == f.district_id)
        districts = (await self.db.execute(district_stmt)).all()
        ids = [row.id for row in districts]

        site_counts = dict((await self.db.execute(
            select(Courtyard.district_id, func.count(Site.id))
            .join(Site, Site.courtyard_id == Courtyard.id)
            .where(Site.is_active.is_(True), Courtyard.district_id.in_(ids), _site_type_clause(f))
            .group_by(Courtyard.district_id)
        )).all()) if ids else {}

        defect_exists = select(ChecklistAnswer.id).where(
            ChecklistAnswer.inspection_id == Inspection.id,
            ChecklistAnswer.result == "defect",
        ).exists()
        issue_exists = select(Issue.id).where(
            Issue.inspection_id == Inspection.id,
        ).exists()
        has_violations = defect_exists | issue_exists

        latest_inspections = (
            select(
                Inspection.id.label("inspection_id"),
                Inspection.site_id,
                func.row_number().over(
                    partition_by=Inspection.site_id,
                    order_by=(Inspection.completed_at.desc(), Inspection.created_at.desc()),
                ).label("rank"),
            )
            .where(
                Inspection.status.in_(DONE_STATUSES),
                Inspection.completed_at >= f.start_utc,
                Inspection.completed_at < f.end_utc,
            )
            .subquery()
        )
        site_quality_rows = (await self.db.execute(
            select(
                Courtyard.district_id,
                func.count(Inspection.id).filter(Site.is_active.is_(True)).label("sites"),
                func.count(Inspection.id)
                .filter(Site.is_active.is_(True) & ~has_violations)
                .label("clean"),
                func.count(Inspection.id)
                .filter(Site.is_active.is_(True) & has_violations)
                .label("defects"),
            )
            .select_from(Inspection)
            .join(latest_inspections, latest_inspections.c.inspection_id == Inspection.id)
            .join(Site, Site.id == Inspection.site_id)
            .join(Courtyard, Courtyard.id == Site.courtyard_id)
            .where(
                latest_inspections.c.rank == 1,
                Courtyard.district_id.in_(ids),
                _site_type_clause(f),
            )
            .group_by(Courtyard.district_id)
        )).all() if ids else []
        site_quality = {row.district_id: row for row in site_quality_rows}

        inspection_rows = (await self.db.execute(
            select(
                Courtyard.district_id,
                func.count(Inspection.id).label("total"),
                func.count(func.distinct(Inspection.site_id))
                .filter(Site.is_active.is_(True)).label("sites"),
                func.count(Inspection.id).filter(~has_violations).label("green"),
                func.count(Inspection.id).filter(has_violations).label("defects"),
            )
            .join(Site, Site.id == Inspection.site_id)
            .join(Courtyard, Courtyard.id == Site.courtyard_id)
            .where(
                Inspection.status.in_(DONE_STATUSES),
                Inspection.completed_at >= f.start_utc,
                Inspection.completed_at < f.end_utc,
                Courtyard.district_id.in_(ids),
                _site_type_clause(f),
            )
            .group_by(Courtyard.district_id)
        )).all() if ids else []
        inspections = {row.district_id: row for row in inspection_rows}

        today = datetime.now(MSK).date()
        issue_rows = (await self.db.execute(
            select(Courtyard.district_id, *issue_bucket_columns(today))
            .join(Site, Site.id == Issue.site_id)
            .join(Courtyard, Courtyard.id == Site.courtyard_id)
            .where(
                Issue.created_at >= f.start_utc,
                Issue.created_at < f.end_utc,
                Courtyard.district_id.in_(ids),
                _site_type_clause(f),
            )
            .group_by(Courtyard.district_id)
        )).all() if ids else []
        issues = {row.district_id: row for row in issue_rows}

        # Статус замечания меняется после его создания: район может передать
        # исправление на проверку, а затем оно может быть принято или возвращено
        # на доработку. Для отчёта за период считаем эти переходы отдельно от
        # среза замечаний, созданных в самом периоде.
        status_event_rows = (await self.db.execute(
            select(
                Courtyard.district_id,
                func.count(IssueStatusHistory.id)
                .filter(IssueStatusHistory.new_status == "fixed")
                .label("fixed_events"),
                func.count(IssueStatusHistory.id)
                .filter(IssueStatusHistory.new_status == "closed")
                .label("closed_events"),
                func.count(IssueStatusHistory.id)
                .filter(IssueStatusHistory.new_status == "revision_needed")
                .label("revision_events"),
            )
            .join(Issue, Issue.id == IssueStatusHistory.issue_id)
            .join(Site, Site.id == Issue.site_id)
            .join(Courtyard, Courtyard.id == Site.courtyard_id)
            .where(
                IssueStatusHistory.created_at >= f.start_utc,
                IssueStatusHistory.created_at < f.end_utc,
                Courtyard.district_id.in_(ids),
                _site_type_clause(f),
            )
            .group_by(Courtyard.district_id)
        )).all() if ids else []
        status_events = {row.district_id: row for row in status_event_rows}

        # Срез устранения берётся на конец выбранного периода. Нельзя читать
        # сегодняшнее Issue.status: повторное формирование июльского отчёта
        # после августовского закрытия иначе переписывает историю. Если
        # переходов ещё не было, начальное состояние замечания — open.
        latest_issue_status = (
            select(
                IssueStatusHistory.issue_id,
                IssueStatusHistory.new_status.label("status"),
                func.row_number().over(
                    partition_by=IssueStatusHistory.issue_id,
                    order_by=(IssueStatusHistory.created_at.desc(), IssueStatusHistory.id.desc()),
                ).label("rank"),
            )
            .where(IssueStatusHistory.created_at < f.end_utc)
            .subquery()
        )
        snapshot_status = func.coalesce(
            latest_issue_status.c.status,
            cast("open", IssueStatusHistory.new_status.type),
        )
        snapshot_issue_rows = (await self.db.execute(
            select(
                Courtyard.district_id,
                func.count(Issue.id).label("snapshot_total"),
                func.count(Issue.id).filter(
                    (Issue.created_at >= f.start_utc)
                    & (Issue.created_at < f.end_utc)
                    & (snapshot_status == "closed")
                ).label("cohort_closed_as_of"),
                func.count(Issue.id).filter(snapshot_status.in_(ON_CHECK_STATUSES)).label("pending_final"),
                func.count(Issue.id).filter(
                    snapshot_status.in_(("open", "assigned", "in_work", "revision_needed"))
                ).label("requires_work"),
                func.count(Issue.id).filter(
                    snapshot_status.in_(OVERDUE_STATUSES)
                    & Issue.due_date.is_not(None)
                    & (Issue.due_date < f.date_to)
                ).label("overdue"),
            )
            .join(Site, Site.id == Issue.site_id)
            .join(Courtyard, Courtyard.id == Site.courtyard_id)
            .outerjoin(
                latest_issue_status,
                (latest_issue_status.c.issue_id == Issue.id) & (latest_issue_status.c.rank == 1),
            )
            .where(
                Issue.created_at < f.end_utc,
                Courtyard.district_id.in_(ids),
                _site_type_clause(f),
            )
            .group_by(Courtyard.district_id)
        )).all() if ids else []
        snapshot_issues = {row.district_id: row for row in snapshot_issue_rows}

        result = []
        for district in districts:
            ins = inspections.get(district.id)
            quality = site_quality.get(district.id)
            iss = issues.get(district.id)
            events = status_events.get(district.id)
            snapshot_issues_row = snapshot_issues.get(district.id)
            found = int(iss.found if iss else 0)
            closed = int(iss.closed if iss else 0)
            total_sites = int(site_counts.get(district.id, 0))
            inspected = int(quality.sites if quality else 0)
            clean_sites = int(quality.clean if quality else 0)
            defect_sites = int(quality.defects if quality else 0)
            snapshot_total = int(snapshot_issues_row.snapshot_total if snapshot_issues_row else 0)
            cohort_closed_as_of = int(
                snapshot_issues_row.cohort_closed_as_of if snapshot_issues_row else 0
            )
            requires_work = int(snapshot_issues_row.requires_work if snapshot_issues_row else 0)
            result.append(StatsDistrictRow(
                district_id=str(district.id), district_name=district.name,
                total_sites=total_sites, sites_inspected=inspected,
                coverage_pct=percent(inspected, total_sites),
                sites_latest_clean=clean_sites,
                sites_latest_with_defects=defect_sites,
                clean_sites_pct=percent(clean_sites, inspected) if inspected else None,
                defect_sites_pct=percent(defect_sites, inspected) if inspected else None,
                inspections_total=int(ins.total if ins else 0),
                inspections_green=int(ins.green if ins else 0),
                inspections_with_defects=int(ins.defects if ins else 0),
                issues_found=found,
                issues_cohort_closed_as_of=cohort_closed_as_of,
                issues_cohort_closed_pct=percent(cohort_closed_as_of, found) if found else None,
                issues_fixed_events=int(events.fixed_events if events else 0),
                issues_closed_events=int(events.closed_events if events else 0),
                issues_revision_events=int(events.revision_events if events else 0),
                issues_pending_final_current=int(snapshot_issues_row.pending_final if snapshot_issues_row else 0),
                issues_requires_work_current=requires_work,
                issues_snapshot_total=snapshot_total,
                issues_requires_work_pct=percent(requires_work, snapshot_total) if snapshot_total else None,
                issues_overdue_current=int(snapshot_issues_row.overdue if snapshot_issues_row else 0),
                issues_closed=closed,
                issues_on_check=int(iss.on_check if iss else 0),
                issues_revision=int(iss.revision if iss else 0),
                issues_in_work=int(iss.in_work if iss else 0),
                issues_open=int(iss.open if iss else 0),
                issues_not_fixed=found - closed,
                issues_overdue=int(iss.overdue if iss else 0),
                issues_closed_pct=percent(closed, found),
            ))
        totals_values = {
            name: sum(getattr(row, name) for row in result)
            for name in StatsDistrictRow.model_fields
            if name not in {
                "district_id", "district_name", "coverage_pct", "clean_sites_pct",
                "defect_sites_pct", "issues_closed_pct", "issues_cohort_closed_pct",
                "issues_requires_work_pct",
            }
        }
        totals = StatsDistrictRow(
            district_id=NIL_UUID, district_name="ВСЕГО", **totals_values,
            coverage_pct=percent(totals_values["sites_inspected"], totals_values["total_sites"]),
            clean_sites_pct=(
                percent(totals_values["sites_latest_clean"], totals_values["sites_inspected"])
                if totals_values["sites_inspected"] else None
            ),
            defect_sites_pct=(
                percent(totals_values["sites_latest_with_defects"], totals_values["sites_inspected"])
                if totals_values["sites_inspected"] else None
            ),
            issues_closed_pct=percent(totals_values["issues_closed"], totals_values["issues_found"]),
            issues_cohort_closed_pct=(
                percent(totals_values["issues_cohort_closed_as_of"], totals_values["issues_found"])
                if totals_values["issues_found"] else None
            ),
            issues_requires_work_pct=(
                percent(totals_values["issues_requires_work_current"], totals_values["issues_snapshot_total"])
                if totals_values["issues_snapshot_total"] else None
            ),
        )
        return StatsDashboardOut(
            period=self._period, generated_at=self.generated_at,
            districts=result, totals=totals,
        )

    async def dynamics(self) -> StatsDynamicsOut:
        f = self.filters
        inspection_day = cast(func.timezone("Europe/Moscow", Inspection.completed_at), Date)
        issue_day = cast(func.timezone("Europe/Moscow", Issue.created_at), Date)
        closure_day = cast(func.timezone("Europe/Moscow", IssueStatusHistory.created_at), Date)

        inspection_stmt = (
            select(inspection_day, func.count(Inspection.id))
            .join(Site, Site.id == Inspection.site_id)
            .join(Courtyard, Courtyard.id == Site.courtyard_id)
            .where(Inspection.status.in_(DONE_STATUSES), Inspection.completed_at >= f.start_utc,
                   Inspection.completed_at < f.end_utc)
            .group_by(inspection_day)
        )
        issue_stmt = (
            select(issue_day, func.count(Issue.id))
            .join(Site, Site.id == Issue.site_id)
            .join(Courtyard, Courtyard.id == Site.courtyard_id)
            .where(Issue.created_at >= f.start_utc, Issue.created_at < f.end_utc)
            .group_by(issue_day)
        )
        closure_stmt = (
            select(closure_day, func.count(IssueStatusHistory.id))
            .join(Issue, Issue.id == IssueStatusHistory.issue_id)
            .join(Site, Site.id == Issue.site_id)
            .join(Courtyard, Courtyard.id == Site.courtyard_id)
            .where(IssueStatusHistory.new_status == "closed",
                   IssueStatusHistory.created_at >= f.start_utc,
                   IssueStatusHistory.created_at < f.end_utc)
            .group_by(closure_day)
        )
        if f.district_id:
            inspection_stmt = inspection_stmt.where(Courtyard.district_id == f.district_id)
            issue_stmt = issue_stmt.where(Courtyard.district_id == f.district_id)
            closure_stmt = closure_stmt.where(Courtyard.district_id == f.district_id)
        if f.site_type:
            inspection_stmt = inspection_stmt.where(Site.type == f.site_type)
            issue_stmt = issue_stmt.where(Site.type == f.site_type)
            closure_stmt = closure_stmt.where(Site.type == f.site_type)

        inspections = dict((await self.db.execute(inspection_stmt)).all())
        issues = dict((await self.db.execute(issue_stmt)).all())
        closures = dict((await self.db.execute(closure_stmt)).all())
        days = []
        current = f.date_from
        while current <= f.date_to:
            days.append(StatsDynamicsDay(
                date=current, inspections=int(inspections.get(current, 0)),
                issues_found=int(issues.get(current, 0)),
                closure_events=int(closures.get(current, 0)),
            ))
            current += timedelta(days=1)
        return StatsDynamicsOut(period=self._period, generated_at=self.generated_at, days=days)

    async def categories(self) -> StatsCategoriesOut:
        f = self.filters
        categories = (await self.db.execute(
            select(IssueCategory).where(IssueCategory.is_active.is_(True))
            .order_by(IssueCategory.sort_order, IssueCategory.name)
        )).scalars().all()
        today = datetime.now(MSK).date()
        stmt = (
            select(Issue.category_id, *issue_bucket_columns(today))
            .join(Site, Site.id == Issue.site_id)
            .join(Courtyard, Courtyard.id == Site.courtyard_id)
            .where(Issue.created_at >= f.start_utc, Issue.created_at < f.end_utc)
            .group_by(Issue.category_id)
        )
        if f.district_id:
            stmt = stmt.where(Courtyard.district_id == f.district_id)
        if f.site_type:
            stmt = stmt.where(Site.type == f.site_type)
        counts = {row.category_id: row for row in (await self.db.execute(stmt)).all()}
        rows = []
        for category in categories:
            count = counts.get(category.id)
            found = int(count.found if count else 0)
            closed = int(count.closed if count else 0)
            rows.append(StatsCategoryRow(
                category_id=str(category.id), name=category.name, sort_order=category.sort_order,
                found=found, closed=closed, on_check=int(count.on_check if count else 0),
                revision=int(count.revision if count else 0),
                in_work=int(count.in_work if count else 0), open=int(count.open if count else 0),
                not_fixed=found - closed, overdue=int(count.overdue if count else 0),
                closed_pct=percent(closed, found),
            ))
        return StatsCategoriesOut(period=self._period, generated_at=self.generated_at, categories=rows)
