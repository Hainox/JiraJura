# -*- coding: utf-8 -*-
"""Разложить CSV со ссылками-приглашениями (см. reissue_invites.py) по файлам
районов для рассылки. Самодостаточный, не импортирует app.models — та же
причина, что и у fix_passwords.py/reissue_invites.py.

Только читает БД (район по district_id), токены не трогает — можно
запускать сколько угодно раз, не инвалидирует уже отправленные ссылки.

Логика распределения по файлам:
  - Роль admin -> отдельный файл admins.csv, независимо от района.
  - Есть район (district_id) -> файл с названием района.
  - Нет района (у Проверяющего район не задан = весь округ) -> отдельный
    файл reviewers_okrug.csv.

ФИО и логины — персональные данные: файлы нужно скачать с сервера,
разослать и удалить с сервера, не оставлять дольше необходимого.

Запуск на сервере:
  docker compose -f docker-compose.prod.yml exec api python split_invites_by_district.py
  docker compose -f docker-compose.prod.yml exec api python split_invites_by_district.py \
      --in /app/uploads/reissued.csv --out-dir /app/uploads/by_district
  # скачать папку с сервера (см. подсказку в конце вывода), разослать, удалить с сервера
"""
import argparse
import asyncio
import csv
import os
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/sao_inspection")


def _safe_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in name).strip().replace(" ", "_")


async def main(in_path: str, out_dir: str):
    with open(in_path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter=";")
        header = next(reader)
        rows = [row for row in reader if row]

    print(f"Прочитано строк: {len(rows)} из {in_path}")

    logins = [row[0] for row in rows]

    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        db_rows = (await db.execute(text(
            "SELECT ui.login, d.name AS district_name "
            "FROM user_invites ui LEFT JOIN districts d ON d.id = ui.district_id "
            "WHERE ui.login = ANY(:logins)"
        ), {"logins": logins})).fetchall()
    await engine.dispose()

    district_by_login = {r.login: r.district_name for r in db_rows}
    not_found = [login for login in logins if login not in district_by_login]
    if not_found:
        print(f"⚠ Не найдены в user_invites (пропущены): {len(not_found)}")
        for login in not_found:
            print(f"   {login}")

    groups: dict[str, list[list[str]]] = defaultdict(list)
    for row in rows:
        login, full_name, role = row[0], row[1], row[2]
        if login not in district_by_login:
            continue
        if role == "admin":
            groups["admins"].append(row)
        else:
            district_name = district_by_login[login]
            key = district_name if district_name else "reviewers_okrug"
            groups[key].append(row)

    os.makedirs(out_dir, exist_ok=True)
    print(f"\nФайлов будет создано: {len(groups)}\n")
    for key, group_rows in sorted(groups.items()):
        fname = os.path.join(out_dir, f"{_safe_filename(key)}.csv")
        with open(fname, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(header)
            w.writerows(group_rows)
        print(f"   {key:30s} {len(group_rows):3d} чел. -> {fname}")

    print(f"\n[DONE] Папка: {out_dir}")
    print("Скачайте, например: docker compose -f docker-compose.prod.yml cp api:" + out_dir + " ./by_district")
    print("(или напрямую с хоста — та же папка примонтирована в backend/uploads)")
    print("После рассылки удалите файлы с сервера (ПДн).")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Разложить CSV со ссылками-приглашениями по районам")
    p.add_argument("--in", dest="in_path", default="/app/uploads/reissued.csv", help="входной CSV (reissue_invites.py)")
    p.add_argument("--out-dir", default="/app/uploads/by_district", help="папка для файлов по районам")
    args = p.parse_args()
    asyncio.run(main(args.in_path, args.out_dir))
