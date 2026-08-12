# -*- coding: utf-8 -*-
"""Проверить, что ссылки в уже разосланном CSV (reissue_invites.py /
split_invites_by_district.py) всё ещё рабочие — читает БД, ничего не меняет.

Для каждой строки берёт токен из ссылки, считает его sha256 и сравнивает с
текущим token_hash в user_invites. Если не совпадает — значит после того как
этот конкретный файл был сгенерирован, для того же человека токен был
перевыпущен ещё раз (например, reissue_invites.py --apply запускали дважды),
и уже разосланная ссылка мертва, хотя сам инвайт в базе валиден.

Запуск на сервере:
  docker compose -f docker-compose.prod.yml exec api python verify_invite_links.py
  docker compose -f docker-compose.prod.yml exec api python verify_invite_links.py --in /app/exports/reissued.csv
"""
import argparse
import asyncio
import csv
import hashlib
import os
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/sao_inspection")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def main(in_path: str):
    with open(in_path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter=";")
        next(reader)
        rows = [row for row in reader if row]

    print(f"Проверяю {len(rows)} ссылок из {in_path}\n")

    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    ok, stale, used, expired, missing = [], [], [], [], []

    async with Session() as db:
        for login, full_name, role, link in rows:
            token = link.rstrip("/").rsplit("/register/", 1)[-1]
            token_hash = _hash_token(token)

            row = (await db.execute(text(
                "SELECT token_hash, used_at, expires_at FROM user_invites WHERE login = :login"
            ), {"login": login})).fetchone()

            if row is None:
                missing.append((login, full_name))
                continue
            if row.used_at is not None:
                used.append((login, full_name))
                continue
            expires_at = row.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < datetime.now(timezone.utc):
                expired.append((login, full_name))
                continue
            if row.token_hash != token_hash:
                stale.append((login, full_name))
                continue
            ok.append((login, full_name))

    await engine.dispose()

    print(f"✅ Рабочие ссылки: {len(ok)}")
    print(f"✔ Уже использованы (человек успешно зарегистрировался): {len(used)}")
    for login, full_name in used:
        print(f"      {full_name}  [{login}]")

    if stale:
        print(f"\n⚠ МЁРТВЫЕ ссылки — токен перевыпущен ПОСЛЕ генерации этого файла "
              f"(нужна повторная генерация и рассылка): {len(stale)}")
        for login, full_name in stale:
            print(f"      {full_name}  [{login}]")

    if expired:
        print(f"\n⚠ Истёк срок действия: {len(expired)}")
        for login, full_name in expired:
            print(f"      {full_name}  [{login}]")

    if missing:
        print(f"\n⚠ Инвайт для этого логина не найден в БД вообще: {len(missing)}")
        for login, full_name in missing:
            print(f"      {full_name}  [{login}]")

    if stale:
        print("\n[ДЕЙСТВИЕ] Мёртвые ссылки нужно перевыпустить заново и разослать только их:")
        print("  docker compose -f docker-compose.prod.yml exec api python reissue_invites.py --apply --out /app/exports/reissued2.csv")
        print("  docker compose -f docker-compose.prod.yml exec api python split_invites_by_district.py --in /app/exports/reissued2.csv --out-dir /app/exports/by_district2")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Проверить валидность уже разосланных ссылок-приглашений")
    p.add_argument("--in", dest="in_path", default="/app/exports/reissued.csv")
    args = p.parse_args()
    asyncio.run(main(args.in_path))
