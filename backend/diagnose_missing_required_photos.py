# -*- coding: utf-8 -*-
"""Диагностика конкретной жалобы «ничего не выходит» (Беговой район,
24.08.2026): по адресу находит обходы площадки, для каждого — совпадает ли
он с серверной проверкой обязательных фото чек-листа (requires_photo,
см. update_inspection в app/routers/inspections.py) и когда реально
загружено каждое фото, чтобы отличить «обход старый, фото добавили только
что» от «фото и правда не хватает, обход не завершить».

Самодостаточный, как diagnose_logins.py — не импортирует app.models.
Только читает, ничего не меняет.

Запуск на сервере:
  docker compose -f docker-compose.prod.yml exec api python diagnose_missing_required_photos.py "Расковой"
  docker compose -f docker-compose.prod.yml exec api python diagnose_missing_required_photos.py "Расковой пер. 19" --district "Беговой"
"""
import argparse
import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/sao_inspection")


async def main(address: str, district: str | None):
    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        params = {"address": f"%{address}%"}
        district_clause = ""
        if district:
            district_clause = "AND d.name ILIKE :district"
            params["district"] = f"%{district}%"

        sites = (await db.execute(text(
            "SELECT s.id, s.type, c.name AS courtyard_name, d.name AS district_name "
            "FROM sites s JOIN courtyards c ON c.id = s.courtyard_id "
            "JOIN districts d ON d.id = c.district_id "
            f"WHERE c.name ILIKE :address {district_clause} "
            "ORDER BY d.name, c.name"
        ), params)).fetchall()

        if not sites:
            print(f"Площадок по адресу «{address}» не найдено (район: {district or 'любой'}).")
            return

        for site in sites:
            print(f"\n=== {site.courtyard_name} ({site.type}), {site.district_name} — site_id={site.id} ===")

            inspections = (await db.execute(text(
                "SELECT i.id, i.status, i.created_at, i.completed_at, i.reviewed_by, "
                "u.full_name AS inspector_name "
                "FROM inspections i JOIN users u ON u.id = i.inspector_id "
                "WHERE i.site_id = :site_id ORDER BY i.created_at DESC"
            ), {"site_id": site.id})).fetchall()

            if not inspections:
                print("  Обходов нет.")
                continue

            for insp in inspections:
                reviewed = "проверен" if insp.reviewed_by else "НЕ проверен"
                print(f"\n  Обход {insp.id}")
                print(f"    Инспектор: {insp.inspector_name} | статус: {insp.status} | {reviewed}")
                print(f"    Создан: {insp.created_at} | завершён: {insp.completed_at}")

                # Та же проверка, что делает backend перед разрешением
                # завершить обход (see missing_photo_items в inspections.py)
                missing = (await db.execute(text(
                    "SELECT ci.question "
                    "FROM checklist_answers ca "
                    "JOIN checklist_items ci ON ci.id = ca.checklist_item_id "
                    "LEFT JOIN photos p ON p.checklist_answer_id = ca.id "
                    "WHERE ca.inspection_id = :insp_id AND ci.requires_photo = TRUE AND p.id IS NULL"
                ), {"insp_id": insp.id})).scalars().all()

                if missing:
                    print(f"    ⚠ НЕ ХВАТАЕТ фото для пункта(ов) чек-листа: {', '.join(missing)}")
                    print("      — именно с этой ошибкой сервер отклонит попытку завершить/пересохранить обход.")
                else:
                    print("    ✓ Все requires_photo-пункты чек-листа имеют фото.")

                photos = (await db.execute(text(
                    "SELECT p.id, p.target_type, p.created_at, p.taken_at, "
                    "ci.question AS checklist_question, iss.title AS issue_title "
                    "FROM photos p "
                    "LEFT JOIN checklist_answers ca ON ca.id = p.checklist_answer_id "
                    "LEFT JOIN checklist_items ci ON ci.id = ca.checklist_item_id "
                    "LEFT JOIN issues iss ON iss.id = p.issue_id "
                    "WHERE p.inspection_id = :insp_id "
                    "OR p.issue_id IN (SELECT id FROM issues WHERE inspection_id = :insp_id) "
                    "ORDER BY p.created_at"
                ), {"insp_id": insp.id})).fetchall()

                if photos:
                    print(f"    Фото ({len(photos)}):")
                    for p in photos:
                        target = p.checklist_question or p.issue_title or p.target_type
                        print(f"      [{p.target_type}] {target} — загружено {p.created_at}, снято (EXIF) {p.taken_at}")
                else:
                    print("    Фото нет вообще.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("address", help="Подстрока адреса двора (courtyards.name), например 'Расковой'")
    parser.add_argument("--district", help="Опционально сузить по названию района")
    args = parser.parse_args()
    asyncio.run(main(args.address, args.district))
