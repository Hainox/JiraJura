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

# Срок по категории — верхняя граница срока по критичности (ISSUE_SLA_DAYS),
# не безусловная замена. По поручению со штаба: МАФ устраняется не дольше,
# чем за 3 дня — раньше это негласно держалось на допущении, что дефекты
# МАФ в чек-листе всегда is_critical=TRUE (→ criticality="high" → 3 дня,
# см. list_maf_deadlines.py), но замечание по МАФ, заведённое вручную с
# criticality="medium"/"low", получало 7/14 дней. Явное правило чинит это —
# но именно как ПОТОЛОК: если замечание по МАФ отдельно помечено
# "critical" (1 день — реальная опасность прямо сейчас), это строже
# штабных 3 дней и не должно ослабляться категорией; берём минимум из
# двух, а не жёстко значение по категории.
CATEGORY_SLA_DAYS: dict[str, int] = {
    "МАФ": 3,
}


def default_due_date(
    criticality: str,
    category_name: str | None = None,
    created_on: date | None = None,
) -> date:
    """Срок устранения по умолчанию: дата создания (МСК) + SLA.

    Срок по критичности (ISSUE_SLA_DAYS) и срок по категории
    (CATEGORY_SLA_DAYS, если для категории задан) — берём меньший (более
    строгий) из двух, см. комментарий у CATEGORY_SLA_DAYS."""
    anchor = created_on or datetime.now(MSK).date()
    days = ISSUE_SLA_DAYS.get(criticality, ISSUE_SLA_DAYS["medium"])
    if category_name in CATEGORY_SLA_DAYS:
        days = min(days, CATEGORY_SLA_DAYS[category_name])
    return anchor + timedelta(days=days)
