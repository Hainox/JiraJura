# -*- coding: utf-8 -*-
"""Массовый персональный сброс пароля по явному списку логинов —
самодостаточный, не импортирует app.models (та же причина, что и у
fix_passwords.py/diagnose_logins.py/reset_shared_passwords.py).

Для случая "люди зарегистрированы, но пароль так и не дошёл до них лично"
(например, вход по ссылке был, а логин/пароль потом никто не передал) —
в отличие от reset_shared_passwords.py (который чинит только группы с
буквально ОДИНАКОВЫМ хэшем пароля), этот скрипт берёт произвольный
список логинов и выдаёт каждому свой новый пароль, независимо от того,
почему они не могут войти.

Без --apply — только отчёт: какие логины найдены/активны, какие не
найдены вовсе (опечатка в списке) или неактивны (отключены админом —
скорее всего, сбрасывать пароль им не нужно, разберитесь сначала).

--apply выдаёт новый пароль только активным найденным аккаунтам, пишет
CSV со ссылками для рассылки. Пароли — та же схема генерации, что и в
admin-панели/reset_shared_passwords.py (без 0/O/1/l/I).

Запуск на сервере:
  docker compose -f docker-compose.prod.yml exec api python reset_passwords_for_logins.py \
    --logins AnikanovaTN,AushevaLA,BoboevKK
  docker compose -f docker-compose.prod.yml exec api python reset_passwords_for_logins.py \
    --logins-file /app/exports/logins.txt --apply --out /app/exports/reset.csv
  # логины-файл — по одному логину на строку
  # скачать CSV с сервера, разослать лично, затем удалить файл с сервера (ПДн)

⚠️ --out/--logins-file ОБЯЗАТЕЛЬНО вне /app/uploads/ — та раздаётся наружу
без авторизации (см. app/services/safe_export.py). Этот CSV содержит
пароли в открытом виде, а не только ФИО/логины — сюда особенно нельзя.
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

# Без 0/O/1/l/I — те же соображения, что и в остальных скриптах сброса:
# пароль почти всегда передаётся человеку на словах/в сообщении.
_PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _gen_password(length: int = 12) -> str:
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def _read_logins(args) -> list[str]:
    logins = []
    if args.logins:
        logins.extend(x.strip() for x in args.logins.split(",") if x.strip())
    if args.logins_file:
        with open(args.logins_file, encoding="utf-8") as f:
            logins.extend(line.strip() for line in f if line.strip())
    # дедуп, регистр логина в БД сохраняется как есть — сравниваем без
    # учёта регистра (та же логика, что и в /login), но в отчёт/CSV
    # кладём логин в исходном написании из базы, не из списка на входе
    seen, out = set(), []
    for l in logins:
        key = l.lower()
        if key not in seen:
            seen.add(key)
            out.append(l)
    return out


async def main(logins: list[str], apply: bool, out_path: str):
    if not logins:
        print("Список логинов пуст — укажите --logins или --logins-file.")
        return

    from app.services.safe_export import reject_uploads_path
    reject_uploads_path(out_path)

    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        rows = (await db.execute(text(
            "SELECT u.id, u.login, u.full_name, u.is_active, d.name AS district_name "
            "FROM users u LEFT JOIN districts d ON d.id = u.district_id "
            "WHERE lower(u.login) = ANY(:logins)"
        ), {"logins": [l.lower() for l in logins]})).fetchall()

        found_lower = {r.login.lower() for r in rows}
        not_found = [l for l in logins if l.lower() not in found_lower]
        active = [r for r in rows if r.is_active]
        inactive = [r for r in rows if not r.is_active]

        print(f"Запрошено логинов: {len(logins)}")
        print(f"Найдено активных: {len(active)}")
        if inactive:
            print(f"Найдено, но ОТКЛЮЧЕНЫ (пароль не сбрасываю, проверьте вручную): {len(inactive)}")
            for r in inactive:
                print(f"   {r.login} — {r.full_name}")
        if not_found:
            print(f"Не найдено в базе вовсе (опечатка в логине?): {len(not_found)}")
            for l in not_found:
                print(f"   {l}")

        if not apply:
            print("\nЭто был dry-run. Для реального сброса пароля активным аккаунтам добавьте --apply.")
            await engine.dispose()
            return

        if not active:
            print("\nНечего сбрасывать — среди найденных нет активных аккаунтов.")
            await engine.dispose()
            return

        out_rows = []
        for r in active:
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

        print(f"\n[DONE] Новый пароль выдан {len(out_rows)} аккаунтам.")
        print(f"Отчёт сохранён: {out_path}")
        print("Скачайте, разошлите лично, затем удалите файл с сервера (ПДн).")
        print("При следующем входе каждому нужно будет сразу задать свой пароль (must_change_password).")

    await engine.dispose()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Массовый персональный сброс пароля по списку логинов")
    p.add_argument("--logins", default="", help="логины через запятую")
    p.add_argument("--logins-file", default="", help="файл с логинами, по одному на строку")
    p.add_argument("--apply", action="store_true", help="выдать новый пароль каждому найденному активному аккаунту")
    p.add_argument("--out", default="exports/reset_by_login.csv", help="куда сохранить CSV с паролями (НЕ внутрь uploads/ — та раздаётся публично)")
    args = p.parse_args()
    asyncio.run(main(_read_logins(args), args.apply, args.out))
