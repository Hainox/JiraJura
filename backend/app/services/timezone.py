# -*- coding: utf-8 -*-
"""Часовой пояс округа — вся система работает по Москве.

Россия не переходит на летнее время с 2014 года, так что фиксированный
UTC+3 корректен круглый год, без обращения к tz-базе.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

MSK = timezone(timedelta(hours=3))


def msk_day_bounds_utc(
    date_from: Optional[date], date_to: Optional[date]
) -> tuple[Optional[datetime], Optional[datetime]]:
    """Переводит календарный диапазон дат (по МСК, обе границы включительно)
    в полуоткрытый интервал [dt_from, dt_to) в UTC для сравнения с
    timestamptz-колонками в БД.

    Наивный `datetime.combine(date_from, datetime.min.time())` без tzinfo
    при сравнении с timestamptz молча трактуется как полночь UTC, то есть
    03:00 по Москве — записи с 00:00 до 03:00 МСК систематически попадают
    не в тот день. Здесь полночь явно берётся по МСК и уже потом переводится
    в UTC.
    """
    dt_from = (
        datetime.combine(date_from, datetime.min.time(), tzinfo=MSK).astimezone(timezone.utc)
        if date_from else None
    )
    dt_to = (
        (datetime.combine(date_to, datetime.min.time(), tzinfo=MSK) + timedelta(days=1)).astimezone(timezone.utc)
        if date_to else None
    )
    return dt_from, dt_to
