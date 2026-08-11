# -*- coding: utf-8 -*-
"""Досоздаёт замечания для дефектов чек-листа, зафиксированных ДО того, как
заработало автосоздание (см. update_inspection в app/routers/inspections.py,
добавлено PR #73) — их результат в ChecklistAnswer.result='defect' есть, а
парного Issue никогда не было, потому что на момент сохранения того обхода
такой логики ещё не существовало.

Обнаружено на живом примере: инспектор отметил "Состояние песочницы" как
"Нарушение", приложил фото — обход давно проверен и закрыт, а раздел
"Замечания по обходу" на карточке пуст, потому что замечания реально нет
в базе, не просто не отобразилось (эту ошибку отображения чинили отдельно
в PR #75 — тут другой случай, данных действительно нет).

Без --apply — только отчёт: сколько дефектов без замечания, по районам.

--apply создаёт Issue для каждого такого дефекта:
  - title = вопрос пункта чек-листа, criticality = high/medium по is_critical
  - created_by = инспектор, проводивший тот обход (по смыслу совпадает с
    тем, кто ставит замечание при живом автосоздании)
  - created_at = created_at самого ChecklistAnswer, а не "сейчас" — иначе
    статистика по периодам задним числом исказится, будто все эти дефекты
    нашли сегодня
  - status='open' — задним числом никакой статус/историю не подделываем,
    просто заводим сам факт, что замечание есть и требует внимания
  - checklist_answer_id проставляется как обычно, тот же UNIQUE-индекс
    (ux_issues_checklist_answer_id) не даст запустить скрипт дважды на
    одни и те же дефекты

Запуск на сервере:
  docker compose -f docker-compose.prod.yml exec api python backfill_missing_issues.py
  docker compose -f docker-compose.prod.yml exec api python backfill_missing_issues.py --apply
"""
import argparse
import asyncio
import os
from collections import Counter

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/sao_inspection")


async def main(apply: bool):
    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        rows = (await db.execute(text(
            "SELECT ca.id AS answer_id, ca.comment, ca.created_at, "
            "       ci.question, ci.is_critical, "
            "       i.id AS inspection_id, i.site_id, i.inspector_id, "
            "       d.name AS district_name "
            "FROM checklist_answers ca "
            "JOIN checklist_items ci ON ci.id = ca.checklist_item_id "
            "JOIN inspections i ON i.id = ca.inspection_id "
            "JOIN sites s ON s.id = i.site_id "
            "JOIN courtyards c ON c.id = s.courtyard_id "
            "JOIN districts d ON d.id = c.district_id "
            "LEFT JOIN issues iss ON iss.checklist_answer_id = ca.id "
            "WHERE ca.result = 'defect' AND iss.id IS NULL "
            "ORDER BY d.name, ca.created_at"
        ))).fetchall()

        print(f"Дефектов чек-листа без замечания: {len(rows)}\n")
        if not rows:
            await engine.dispose()
            return

        by_district = Counter(r.district_name for r in rows)
        for name, cnt in sorted(by_district.items(), key=lambda x: -x[1]):
            print(f"   {name:25s} {cnt}")

        if not apply:
            print("\nЭто был dry-run. Для создания замечаний добавьте --apply.")
            await engine.dispose()
            return

        created = 0
        for r in rows:
            criticality = "high" if r.is_critical else "medium"
            await db.execute(text(
                "INSERT INTO issues "
                "(inspection_id, site_id, checklist_answer_id, title, description, "
                " criticality, status, created_by, created_at) "
                "VALUES (:inspection_id, :site_id, :answer_id, :title, :description, "
                "        :criticality, 'open', :created_by, :created_at) "
                "ON CONFLICT (checklist_answer_id) WHERE checklist_answer_id IS NOT NULL DO NOTHING"
            ), {
                "inspection_id": r.inspection_id, "site_id": r.site_id, "answer_id": r.answer_id,
                "title": r.question, "description": r.comment,
                "criticality": criticality, "created_by": r.inspector_id, "created_at": r.created_at,
            })
            created += 1
        await db.commit()
        print(f"\n[DONE] Создано замечаний: {created}")

    await engine.dispose()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Досоздать замечания для дефектов чек-листа без пары Issue")
    p.add_argument("--apply", action="store_true", help="реально создать замечания (иначе только отчёт)")
    args = p.parse_args()
    asyncio.run(main(args.apply))
