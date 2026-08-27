# -*- coding: utf-8 -*-
"""Проставляет срок устранения (due_date) замечаниям, у которых он до сих
пор NULL — по запросу к докладу: в all_open_by_category.csv часть строк
показывала "Срок устранения: не задан" и пустую "Дней до/после срока".

Причина — историческая, не текущий баг: раньше due_date не проставлялся
вообще ни на одном пути создания замечания (см. докстринг
app/services/issues.py). Позже это починили — create_issue (issues.py) и
автосоздание из чек-листа (inspections.py) теперь сами вызывают
default_due_date() при создании. Но замечания, заведённые ДО этой правки,
так и остались с NULL — их правка не касалась задним числом, и мы их
никогда не бэкфиллили (аналогичный случай — backfill_missing_issues.py,
только там про сами замечания, здесь — про их срок).

Без --apply — только отчёт: сколько замечаний без срока, по критичности.

--apply считает срок так же, как считает default_due_date() при живом
создании (SLA по критичности из ISSUE_SLA_DAYS), но датой отсчёта берёт
не "сейчас", а дату создания самого замечания (created_at, переведённую в
МСК) — иначе часть просроченных задним числом внезапно оказалась бы ещё
"не просроченной" только потому, что бэкфилл запустили сегодня.

Важно: due_date можно снять и намеренно — update_issue (routers/issues.py)
по model_fields_set отличает "поле не прислали" от "прислали null", то
есть проверяющий/админ может явно очистить срок через PATCH. Бэкфилл не
должен путать такой осознанный null с "срок никогда не проставлялся" —
поэтому берём только строки с updated_at IS NULL: эта колонка не имеет
default и обновляется исключительно внутри update_issue (который сам же
безусловно проставляет issue.updated_at = now() при любом PATCH), так что
NULL здесь гарантирует "замечание с момента создания никто не трогал", а
не просто "давно не трогали". Замечания с уже непустым updated_at в отчёте
показаны отдельно и бэкфиллом не трогаются — если среди них тоже есть
случаи с due_date IS NULL, это тот самый неотличимый случай, разбирать
вручную.

Самодостаточный по духу остальных скриптов в backend/, но, в отличие от
них, импортирует app.services.issues.default_due_date — это совсем
лёгкий модуль (только datetime + app.services.timezone, тоже без внешних
зависимостей), а SLA-таблица (ISSUE_SLA_DAYS) там намеренно вынесена в
одно место и явно согласована с владельцем продукта — переизобретать её
здесь через сырой SQL CASE значило бы рисковать разойтись, если шкалу
когда-нибудь поменяют.

Запуск на сервере:
  docker compose -f docker-compose.prod.yml exec api python backfill_issue_due_dates.py
  docker compose -f docker-compose.prod.yml exec api python backfill_issue_due_dates.py --apply
"""
import argparse
import asyncio
import os
from collections import Counter

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
            "SELECT id, criticality, status, created_at "
            "FROM issues WHERE due_date IS NULL AND updated_at IS NULL"
        ))).fetchall()
        touched_count = (await db.execute(text(
            "SELECT count(*) FROM issues WHERE due_date IS NULL AND updated_at IS NOT NULL"
        ))).scalar_one()

        if not rows:
            print("Замечаний без срока устранения (нетронутых с момента создания) не найдено — бэкфилл не нужен.")
            if touched_count:
                print(f"Но есть {touched_count} замечаний с due_date IS NULL, которые уже редактировались — "
                      f"скрипт их не трогает (возможен осознанный null), разбирать вручную.")
            return

        by_criticality = Counter(r.criticality for r in rows)
        by_status = Counter(r.status for r in rows)
        print(f"Замечаний без срока устранения (нетронутых с момента создания): {len(rows)}")
        print("По критичности:")
        for crit, count in by_criticality.most_common():
            print(f"  {crit}: {count}")
        print("По статусу:")
        for status, count in by_status.most_common():
            print(f"  {status}: {count}")
        if touched_count:
            print(f"\nЕщё {touched_count} замечаний с due_date IS NULL уже редактировались после создания — "
                  f"пропущены (возможен осознанный null), разбирать вручную.")

        if not apply:
            print("\nЭто отчёт. Чтобы проставить сроки — повторите с --apply.")
            return

        updated = 0
        for r in rows:
            created_on = r.created_at.astimezone(MSK).date()
            due_date = default_due_date(r.criticality, created_on=created_on)
            # due_date IS NULL в UPDATE — на случай, если между SELECT и этим
            # запросом кто-то уже проставил срок вручную через PATCH: тогда
            # обновление просто не сработает (rowcount == 0), а не затрёт
            # только что введённое значение.
            result = await db.execute(
                text("UPDATE issues SET due_date = :due_date WHERE id = :id AND due_date IS NULL"),
                {"due_date": due_date, "id": r.id},
            )
            if result.rowcount:
                updated += 1
        await db.commit()
        print(f"\nПроставлен срок устранения {updated} замечаниям.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="реально проставить сроки (без флага — только отчёт)")
    args = parser.parse_args()
    asyncio.run(main(args.apply))
