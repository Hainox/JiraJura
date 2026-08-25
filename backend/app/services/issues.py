# -*- coding: utf-8 -*-
"""Общие правила по замечаниям (Issue), используемые из нескольких роутеров
(issues.py — ручное создание; inspections.py — автосоздание из чек-листа).

Срок устранения раньше не проставлялся вообще ни на одном пути создания
замечания — due_date оставался NULL, и вся логика "просрочено" (которая
явно исключает NULL) молча никогда не срабатывала. Теперь срок считается
автоматически по критичности при создании и остаётся свободно
редактируемым проверяющим/админом (см. update_issue в issues.py) — как
раньше, просто с разумным значением по умолчанию, а не пустотой.
"""
from datetime import date, datetime, timedelta

from app.services.timezone import MSK

# Дней на устранение от даты создания, по критичности замечания.
# Согласовано с владельцем продукта — не выдумывать заново при следующей
# правке, а согласовывать новые значения так же явно.
ISSUE_SLA_DAYS: dict[str, int] = {
    "critical": 1,
    "high": 3,
    "medium": 7,
    "low": 14,
}


def default_due_date(criticality: str, created_on: date | None = None) -> date:
    """Срок устранения по умолчанию: дата создания (МСК) + SLA по критичности."""
    anchor = created_on or datetime.now(MSK).date()
    days = ISSUE_SLA_DAYS.get(criticality, ISSUE_SLA_DAYS["medium"])
    return anchor + timedelta(days=days)
