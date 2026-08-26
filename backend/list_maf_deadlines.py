# -*- coding: utf-8 -*-
"""Список открытых замечаний по МАФ со сроками устранения — по запросу со
штаба 26.08.2026 (Кануков Д.М., зам. префекта САО): главам районов нужно
видеть срок по каждому конкретному МАФ, чтобы подтвердить/скорректировать
дату устранения. Не общая статистика, а адресный список, который можно
выгрузить и разослать по районам.

Самодостаточный, как diagnose_logins.py/reissue_invites.py — не
импортирует app.models, только читает БД напрямую.

Критичность "high" (не критично, но требует внимания) уже соответствует
озвученным на штабе "3 дня на устранение сломанного МАФ" — см.
ISSUE_SLA_DAYS в app/services/issues.py (critical=1, high=3, medium=7,
low=14). Если штаб утвердит другую шкалу (называли 1-3-5-7) — это
отдельная правка, здесь просто читаются уже проставленные due_date, какая
бы шкала их ни считала.

Запуск на сервере:
  # общий отчёт по всем районам, только консоль:
  docker compose -f docker-compose.prod.yml exec api python list_maf_deadlines.py

  # выгрузка в CSV (обязательно вне uploads/ — см. safe_export.py):
  docker compose -f docker-compose.prod.yml exec api python list_maf_deadlines.py --out /app/exports/maf_deadlines.csv
  # скачать: docker compose -f docker-compose.prod.yml cp api:/app/exports/maf_deadlines.csv .

  # только один район:
  docker compose -f docker-compose.prod.yml exec api python list_maf_deadlines.py --district "Беговой" --out /app/exports/maf_deadlines_begovoy.csv

  # другая категория вместо МАФ (например, всё сразу):
  docker compose -f docker-compose.prod.yml exec api python list_maf_deadlines.py --category "" --out /app/exports/all_open.csv
"""
import argparse
import asyncio
import csv
import os
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/sao_inspection")

CRIT_LABELS = {"critical": "Критическая", "high": "Высокая", "medium": "Средняя", "low": "Низкая"}
STATUS_LABELS = {
    "open": "Открыто", "assigned": "Назначено", "in_work": "В работе",
    "fixed": "Исправлено", "control": "На контроле", "closed": "Закрыто",
}


async def main(district: str | None, category: str | None, out: str | None):
    if out:
        from app.services.safe_export import reject_uploads_path, ensure_parent_dir
        reject_uploads_path(out)
        ensure_parent_dir(out)

    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    params: dict = {}
    clauses = ["i.status NOT IN ('fixed', 'closed')"]

    if district:
        clauses.append("d.name ILIKE :district")
        params["district"] = f"%{district}%"

    # category="" (пустая строка) явно снимает фильтр по категории —
    # иначе по умолчанию смотрим именно МАФ, как просили на штабе.
    if category is None:
        category = "МАФ"
    if category:
        clauses.append("ic.name = :category")
        params["category"] = category

    where = " AND ".join(clauses)

    async with Session() as db:
        rows = (await db.execute(text(
            "SELECT d.name AS district_name, c.name AS courtyard_name, s.type AS site_type, "
            "ic.name AS category_name, i.title, i.criticality, i.status, "
            "i.created_at::date AS created_date, i.due_date, i.executor_name, "
            "u.full_name AS created_by_name "
            "FROM issues i "
            "JOIN sites s ON s.id = i.site_id "
            "JOIN courtyards c ON c.id = s.courtyard_id "
            "JOIN districts d ON d.id = c.district_id "
            "JOIN issue_categories ic ON ic.id = i.category_id "
            "JOIN users u ON u.id = i.created_by "
            f"WHERE {where} "
            "ORDER BY d.name, i.due_date NULLS LAST, c.name"
        ), params)).fetchall()

    if not rows:
        print(f"Открытых замечаний{' по категории «' + category + '»' if category else ''} "
              f"{'в районе «' + district + '»' if district else 'по всем районам'} не найдено.")
        return

    today = date.today()
    fieldnames = [
        "Район", "Двор", "Тип площадки", "Категория", "Замечание",
        "Критичность", "Статус", "Дата выявления", "Срок устранения",
        "Дней до/после срока", "Исполнитель", "Кем выявлено",
    ]

    def row_dict(r):
        days_left = (r.due_date - today).days if r.due_date else None
        return {
            "Район": r.district_name,
            "Двор": r.courtyard_name,
            "Тип площадки": r.site_type,
            "Категория": r.category_name,
            "Замечание": r.title,
            "Критичность": CRIT_LABELS.get(r.criticality, r.criticality),
            "Статус": STATUS_LABELS.get(r.status, r.status),
            "Дата выявления": r.created_date.isoformat(),
            "Срок устранения": r.due_date.isoformat() if r.due_date else "не задан",
            "Дней до/после срока": days_left if days_left is not None else "",
            "Исполнитель": r.executor_name or "",
            "Кем выявлено": r.created_by_name,
        }

    if out:
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            for r in rows:
                writer.writerow(row_dict(r))
        overdue = sum(1 for r in rows if r.due_date and r.due_date < today)
        print(f"Записей: {len(rows)}, из них просрочено: {overdue}. Сохранено в {out}")
    else:
        current_district = None
        for r in rows:
            if r.district_name != current_district:
                current_district = r.district_name
                print(f"\n=== {current_district} ===")
            d = row_dict(r)
            overdue_mark = " ⚠ ПРОСРОЧЕНО" if isinstance(d["Дней до/после срока"], int) and d["Дней до/после срока"] < 0 else ""
            print(
                f"  [{d['Критичность']}] {d['Двор']} ({d['Тип площадки']}) — {d['Замечание']}\n"
                f"    Статус: {d['Статус']} | Срок: {d['Срок устранения']} | "
                f"Осталось дней: {d['Дней до/после срока']}{overdue_mark} | "
                f"Исполнитель: {d['Исполнитель'] or '—'}"
            )
        overdue = sum(1 for r in rows if r.due_date and r.due_date < today)
        print(f"\nВсего: {len(rows)} записей, просрочено: {overdue}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--district", help="фильтр по району (частичное совпадение)")
    parser.add_argument("--category", default=None, help='категория нарушения (по умолчанию "МАФ"; пустая строка снимает фильтр)')
    parser.add_argument("--out", help="путь к CSV (вне uploads/); без этого флага — только вывод в консоль")
    args = parser.parse_args()
    asyncio.run(main(args.district, args.category, args.out))
