# -*- coding: utf-8 -*-
"""Найти группы аккаунтов с ОДИНАКОВЫМ password_hash и выдать каждому
персональный пароль — самодостаточный, не импортирует app.models (та же
причина, что и у fix_passwords.py/diagnose_logins.py).

Как появляются такие группы: diagnose_logins.py --apply сбрасывает ВСЕ
найденные битые аккаунты за один запуск на ОДИН общий временный пароль
(это осознанно — иначе пришлось бы придумывать и печатать N паролей).
Этот временный пароль печатается только в терминал того, кто запускал
--apply, и нигде больше не сохраняется. Если его не передали лично
КАЖДОМУ из затронутых людей — они физически не могут узнать свой пароль,
и вход будет падать с "неверный логин или пароль", хотя сам аккаунт
исправен. Раз diagnose_logins.py запускали больше одного раза, в базе
может быть несколько таких групп с разными общими паролями.

Это НЕ баг безопасности per se (bcrypt-коллизия исключена: одинаковый
хэш означает, что он был буквально скопирован при массовом сбросе, а не
получен независимым хэшированием) — но раз общий пароль потерян, чинить
проще персональным сбросом каждому.

--apply даёт каждому найденному в такой группе аккаунту свой уникальный
пароль (без похожих символов, тот же генератор что и в admin-панели) +
must_change_password=true, и пишет CSV со ссылками для рассылки лично.

Запуск на сервере:
  docker compose -f docker-compose.prod.yml exec api python reset_shared_passwords.py
  docker compose -f docker-compose.prod.yml exec api python reset_shared_passwords.py --apply --out /app/exports/reset_shared.csv
  # скачать файл, разослать лично, удалить с сервера (ПДн)

⚠️ --out ОБЯЗАТЕЛЬНО вне /app/uploads/ — та раздаётся наружу без
авторизации (см. app/services/safe_export.py). Пароли в открытом виде —
особенно нельзя.
"""
import argparse
import asyncio
import csv
import os
import secrets

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/sao_inspection")

# Без 0/O/1/l/I — те же соображения, что и в reset_user_password (auth.py):
# пароль почти всегда передаётся человеку на словах/в сообщении.
_PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _gen_password(length: int = 12) -> str:
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


async def main(apply: bool, out_path: str):
    from app.services.safe_export import reject_uploads_path
    reject_uploads_path(out_path)

    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        groups = (await db.execute(text(
            "SELECT password_hash, COUNT(*) AS n "
            "FROM users WHERE is_active GROUP BY password_hash HAVING COUNT(*) > 1"
        ))).fetchall()

        if not groups:
            print("Групп с общим password_hash не найдено — можно не запускать.")
            await engine.dispose()
            return

        print(f"Групп с общим паролем: {len(groups)}\n")
        affected = []
        for g in groups:
            rows = (await db.execute(text(
                "SELECT u.id, u.login, u.full_name, d.name AS district_name "
                "FROM users u LEFT JOIN districts d ON d.id = u.district_id "
                "WHERE u.password_hash = :h ORDER BY u.full_name"
            ), {"h": g.password_hash})).fetchall()
            print(f"  Хэш {g.password_hash[:20]}... — {len(rows)} чел.")
            affected.extend(rows)

        print(f"\nВсего затронуто аккаунтов: {len(affected)}")

        if not apply:
            print("\nЭто был dry-run. Для персонального сброса пароля каждому добавьте --apply.")
            await engine.dispose()
            return

        out_rows = []
        for r in affected:
            new_password = _gen_password()
            new_hash = pwd_context.hash(new_password)
            await db.execute(text(
                "UPDATE users SET password_hash = :h, must_change_password = true WHERE id = :id"
            ), {"h": new_hash, "id": r.id})
            out_rows.append([r.login, r.full_name, r.district_name or "", new_password])
        await db.commit()

        out_rows.sort(key=lambda row: (row[2], row[1]))
        from app.services.safe_export import ensure_parent_dir
        ensure_parent_dir(out_path)
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Логин", "ФИО", "Район", "Новый пароль"])
            w.writerows(out_rows)

        print(f"\n[DONE] Персональный пароль выдан {len(out_rows)} аккаунтам.")
        print(f"Отчёт сохранён: {out_path}")
        print("Скачайте, разошлите лично, затем удалите файл с сервера (ПДн).")
        print("При следующем входе каждому нужно будет сразу задать свой пароль (must_change_password).")

    await engine.dispose()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Найти и починить аккаунты с общим (потерянным) паролем")
    p.add_argument("--apply", action="store_true", help="выдать персональный пароль каждому найденному")
    p.add_argument("--out", default="exports/reset_shared.csv", help="куда сохранить CSV с паролями (НЕ внутрь uploads/ — та раздаётся публично)")
    args = p.parse_args()
    asyncio.run(main(args.apply, args.out))
