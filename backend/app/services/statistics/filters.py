"""Calendar periods and role-based scope for statistics v2."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException

from app.models import User
from app.services.timezone import MSK, msk_day_bounds_utc

ALL_TIME_START = date(2026, 6, 1)


@dataclass(frozen=True)
class StatisticsFilter:
    date_from: date
    date_to: date
    start_utc: datetime
    end_utc: datetime
    district_id: UUID | None
    site_type: str | None = None


def current_week() -> tuple[date, date]:
    today = datetime.now(MSK).date()
    return today - timedelta(days=today.weekday()), today


def previous_full_week() -> tuple[date, date]:
    this_monday, _ = current_week()
    return this_monday - timedelta(days=7), this_monday - timedelta(days=1)


def build_filter(
    current_user: User,
    date_from: date | None,
    date_to: date | None,
    district_id: UUID | None,
    *,
    default_previous_week: bool = False,
    all_time: bool = False,
    site_type: str | None = None,
) -> StatisticsFilter:
    default_from, default_to = previous_full_week() if default_previous_week else current_week()
    start_date = ALL_TIME_START if all_time else date_from or default_from
    end_date = datetime.now(MSK).date() if all_time else date_to or default_to
    if start_date > end_date:
        raise HTTPException(422, "date_from не может быть позже date_to")
    if not all_time and (end_date - start_date).days > 365:
        raise HTTPException(422, "Максимальный период статистики — 366 дней")

    effective_district = district_id
    if current_user.role == "reviewer" and current_user.district_id is not None:
        effective_district = current_user.district_id
    start_utc, end_utc = msk_day_bounds_utc(start_date, end_date)
    assert start_utc is not None and end_utc is not None
    return StatisticsFilter(start_date, end_date, start_utc, end_utc, effective_district, site_type)
