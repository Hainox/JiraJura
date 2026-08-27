# -*- coding: utf-8 -*-
"""Список открытых замечаний со сроками устранения — по запросу со штаба
26.08.2026 (Кануков Д.М., зам. префекта САО): главам районов нужно видеть
срок по каждому конкретному замечанию, чтобы подтвердить/скорректировать
дату устранения. Не общая статистика, а адресный список, который можно
выгрузить и разослать по районам.

Изначально писался под МАФ (--category по умолчанию "МАФ"), но название
файла шире не переименовывал — --category "" снимает фильтр и даёт полный
список по всем категориям, а --sort category группирует его по категориям
вместо районов (для доклада: "полный список открытых замечаний,
сгруппированный по категориям" — тот же запрос, другая сортировка).

Самодостаточный, как diagnose_logins.py/reissue_invites.py — не
импортирует app.models, только читает БД напрямую.

Критичность "high" (не критично, но требует внимания) уже соответствует
озвученным на штабе "3 дня на устранение сломанного МАФ" — см.
ISSUE_SLA_DAYS в app/services/issues.py (critical=1, high=3, medium=7,
low=14). Если штаб утвердит другую шкалу (называли 1-3-5-7) — это
отдельная правка, здесь просто читаются уже проставленные due_date, какая
бы шкала их ни считала.

Запуск на сервере:
  # общий отчёт по всем районам, только консоль (категория по умолчанию — МАФ):
  docker compose -f docker-compose.prod.yml exec api python list_maf_deadlines.py

  # выгрузка в CSV (обязательно вне uploads/ — см. safe_export.py):
  docker compose -f docker-compose.prod.yml exec api python list_maf_deadlines.py --out /app/exports/maf_deadlines.csv
  # скачать: docker compose -f docker-compose.prod.yml cp api:/app/exports/maf_deadlines.csv .

  # только один район:
  docker compose -f docker-compose.prod.yml exec api python list_maf_deadlines.py --district "Беговой" --out /app/exports/maf_deadlines_begovoy.csv

  # полный список по всем категориям, сгруппированный по районам (по умолчанию):
  docker compose -f docker-compose.prod.yml exec api python list_maf_deadlines.py --category "" --out /app/exports/all_open_by_district.csv

  # тот же полный список, но сгруппированный по категориям — для доклада:
  docker compose -f docker-compose.prod.yml exec api python list_maf_deadlines.py --category "" --sort category --out /app/exports/all_open_by_category.csv

  # отдельно детские / отдельно спортивные площадки — для доклада с разбивкой:
  docker compose -f docker-compose.prod.yml exec api python list_maf_deadlines.py --category "" --sort category --site-type "Детская площадка" --out /app/exports/detskie_by_category.csv
  docker compose -f docker-compose.prod.yml exec api python list_maf_deadlines.py --category "" --sort category --site-type "Спортивная площадка" --out /app/exports/sportivnye_by_category.csv
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


async def main(district: str | None, category: str | None, out: str | None, sort: str,
                site_type: str | None):
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

    if site_type:
        clauses.append("s.type = :site_type")
        params["site_type"] = site_type

    where = " AND ".join(clauses)
    order_by = (
        "ic.name, d.name, i.due_date NULLS LAST, c.name" if sort == "category"
        else "d.name, i.due_date NULLS LAST, c.name"
    )

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
            f"ORDER BY {order_by}"
        ), params)).fetchall()

    if not rows:
        print(f"Открытых замечаний{' по категории «' + category + '»' if category else ''}"
              f"{' (' + site_type + ')' if site_type else ''} "
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
        current_group = None
        group_field = "category_name" if sort == "category" else "district_name"
        for r in rows:
            group_value = getattr(r, group_field)
            if group_value != current_group:
                current_group = group_value
                print(f"\n=== {current_group} ===")
            d = row_dict(r)
            overdue_mark = " ⚠ ПРОСРОЧЕНО" if isinstance(d["Дней до/после срока"], int) and d["Дней до/после срока"] < 0 else ""
            location = f"{d['Район']} — {d['Двор']}" if sort == "category" else d["Двор"]
            print(
                f"  [{d['Критичность']}] {location} ({d['Тип площадки']}) — {d['Замечание']}\n"
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
    parser.add_argument("--sort", choices=["district", "category"], default="district",
                         help="группировка списка: по районам (по умолчанию) или по категориям замечания")
    parser.add_argument("--site-type", choices=["Детская площадка", "Спортивная площадка"], default=None,
                         help="фильтр по типу площадки (по умолчанию — детские и спортивные вместе)")
    args = parser.parse_args()
    asyncio.run(main(args.district, args.category, args.out, args.sort, args.site_type))
