# -*- coding: utf-8 -*-
"""Пересчитывает срок устранения (due_date) уже заведённых замечаний по
категории МАФ под новый потолок "не дольше 3 дней" (см. CATEGORY_SLA_DAYS
в app/services/issues.py, поручение со штаба) — критичные (1 день)
остаются строже и не трогаются, "high" (тоже 3 дня) не меняется, а
"medium"/"low" (раньше 7/14) укорачиваются до 3.

Зачем отдельный скрипт, а не backfill_issue_due_dates.py: тот бэкфиллит
только due_date IS NULL (срок никогда не проставлялся). Здесь другой
случай — у замечания уже ЕСТЬ due_date, но посчитан он по старому правилу
(SLA по критичности: high=3, medium=7, low=14), и его нужно ЗАМЕНИТЬ на
срок по категории, если тот строже. Разные условия отбора — разные
скрипты, чтобы не превращать один файл в мешанину из двух несвязанных
условий WHERE.

Тот же принцип безопасности, что и в backfill_issue_due_dates.py: трогаем
только замечания с updated_at IS NULL — эта колонка не имеет default и
обновляется исключительно внутри update_issue при любом PATCH, так что
NULL здесь гарантирует "замечание с момента создания никто не трогал".
Если проверяющий/админ уже вручную скорректировал срок по такому
замечанию (даже если случайно совпал со старым правилом) — это осознанное
решение человека, бэкфилл его не перезаписывает.

Без --apply — только отчёт: сколько замечаний по МАФ и с каким текущим
сроком будет пересчитано, до/после.

Запуск на сервере:
  docker compose -f docker-compose.prod.yml exec api python backfill_maf_due_dates.py
  docker compose -f docker-compose.prod.yml exec api python backfill_maf_due_dates.py --apply
"""
import argparse
import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.services.issues import default_due_date
from app.services.timezone import MSK

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/sao_inspection")


async def main(apply: bool):
    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        rows = (await db.execute(text(
            "SELECT iss.id, iss.criticality, iss.status, iss.created_at, iss.due_date "
            "FROM issues iss JOIN issue_categories ic ON ic.id = iss.category_id "
            "WHERE ic.name = 'МАФ' AND iss.status != 'closed' AND iss.updated_at IS NULL "
            "ORDER BY iss.created_at"
        ))).fetchall()
        touched_count = (await db.execute(text(
            "SELECT count(*) FROM issues iss JOIN issue_categories ic ON ic.id = iss.category_id "
            "WHERE ic.name = 'МАФ' AND iss.status != 'closed' AND iss.updated_at IS NOT NULL"
        ))).scalar_one()

        to_change = []
        already_correct = 0
        for r in rows:
            created_on = r.created_at.astimezone(MSK).date()
            new_due = default_due_date(r.criticality, "МАФ", created_on=created_on)
            if r.due_date == new_due:
                already_correct += 1
            else:
                to_change.append((r, new_due))

        print(f"Открытых замечаний по МАФ (нетронутых с момента создания): {len(rows)}")
        print(f"  уже с верным сроком (3 дня): {already_correct}")
        print(f"  требуют пересчёта: {len(to_change)}")
        for r, new_due in to_change:
            print(f"    {r.id}  {r.criticality:<9}  было {r.due_date}  →  станет {new_due}")
        if touched_count:
            print(f"\nЕщё {touched_count} открытых замечаний по МАФ уже редактировались после создания — "
                  f"пропущены (возможна осознанная правка срока человеком), разбирать вручную.")

        if not to_change:
            print("\nПересчитывать нечего.")
            return

        if not apply:
            print("\nЭто отчёт. Чтобы пересчитать сроки — повторите с --apply.")
            return

        updated = 0
        for r, new_due in to_change:
            # updated_at IS NULL в UPDATE — та же защита от гонки с
            # PATCH между SELECT и этим запросом, что и в
            # backfill_issue_due_dates.py.
            result = await db.execute(
                text("UPDATE issues SET due_date = :due_date WHERE id = :id AND updated_at IS NULL"),
                {"due_date": new_due, "id": r.id},
            )
            if result.rowcount:
                updated += 1
        await db.commit()
        print(f"\nПересчитан срок устранения {updated} замечаниям по МАФ.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="реально пересчитать сроки (без флага — только отчёт)")
    args = parser.parse_args()
    asyncio.run(main(args.apply))
