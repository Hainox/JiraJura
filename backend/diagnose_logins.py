# -*- coding: utf-8 -*-
"""Диагностика причин сбоя входа — самодостаточный, не импортирует app.models
(та же причина, что и у fix_passwords.py: не триггерить конфигурацию
мапперов SQLAlchemy на случай, если модели временно не грузятся).

Находит:
  - аккаунты с повреждённым/некорректным password_hash (не проходит формат
    bcrypt) — именно это роняло вход с "ошибка сервера" до фикса
    verify_password() в auth.py;
  - активные приглашения без завершённой регистрации (человек никогда не
    задавал себе пароль — не сможет войти в принципе, это не баг, а просто
    незаконченная выдача доступа);
  - деактивированные аккаунты, чей логин НЕ начинается с deleted_ (обычный
    софт-делит переименовывает логин — если логин обычный, а is_active
    false, стоит проверить вручную, почему).

Без --apply — только отчёт, ничего не меняет.
Запуск на сервере:
  docker compose -f docker-compose.prod.yml exec api python diagnose_logins.py
  docker compose -f docker-compose.prod.yml exec api python diagnose_logins.py --apply
    (--apply сбрасывает пароль ТОЛЬКО найденным битым аккаунтам на один
    общий временный пароль + must_change_password=true — им придётся
    задать свой при следующем входе; остальных пользователей не трогает)
"""
import argparse
import asyncio
import os
import re
import secrets

from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
BCRYPT_RE = re.compile(r"^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/sao_inspection")


async def main(apply: bool):
    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        rows = (await db.execute(text(
            "SELECT id, login, full_name, role, is_active, password_hash "
            "FROM users ORDER BY full_name"
        ))).fetchall()

        print(f"Всего пользователей в БД: {len(rows)}\n")

        broken = []
        inactive_not_deleted = []
        for uid, login, full_name, role, is_active, pw_hash in rows:
            if not is_active:
                if not login.startswith("deleted_"):
                    inactive_not_deleted.append((login, full_name))
                continue
            if not pw_hash or not BCRYPT_RE.match(pw_hash):
                broken.append((uid, login, full_name, role, pw_hash))

        if broken:
            print(f"⚠ Аккаунтов с повреждённым/некорректным хэшем пароля: {len(broken)}")
            for uid, login, full_name, role, pw_hash in broken:
                preview = repr((pw_hash or "")[:20])
                print(f"   {login:25s} {full_name:35s} {role:10s} hash={preview}")
        else:
            print("✓ Повреждённых хэшей паролей не найдено.")

        if inactive_not_deleted:
            print(f"\n⚠ Деактивированы, но логин не похож на софт-делит (is_active=false, "
                  f"логин не deleted_*) — стоит проверить вручную: {len(inactive_not_deleted)}")
            for login, full_name in inactive_not_deleted:
                print(f"   {login:25s} {full_name}")

        invites = (await db.execute(text(
            "SELECT login, full_name, expires_at FROM user_invites "
            "WHERE used_at IS NULL ORDER BY full_name"
        ))).fetchall()
        if invites:
            print(f"\nПриглашения без завершённой регистрации (человек ещё не задавал "
                  f"себе пароль): {len(invites)}")
            for login, full_name, expires_at in invites:
                print(f"   {login:25s} {full_name:35s} истекает {expires_at}")

        if not apply:
            if broken:
                print(f"\nЭто был dry-run. Для сброса пароля {len(broken)} битым "
                      f"аккаунтам добавьте --apply.")
            await engine.dispose()
            return

        if not broken:
            print("\nБитых хэшей нет — нечего исправлять.")
            await engine.dispose()
            return

        new_password = secrets.token_urlsafe(6)
        new_hash = pwd_context.hash(new_password)
        assert pwd_context.verify(new_password, new_hash), \
            "FATAL: сгенерированный хэш не проходит собственную проверку"

        for uid, login, full_name, role, pw_hash in broken:
            await db.execute(text(
                "UPDATE users SET password_hash = :h, must_change_password = true "
                "WHERE id = :id"
            ), {"h": new_hash, "id": uid})
        await db.commit()

        print(f"\n[DONE] Сброшен пароль {len(broken)} аккаунтам на временный: {new_password}")
        print("Передайте его лично затронутым людям — при входе им нужно будет сразу задать свой.")
        for uid, login, full_name, role, pw_hash in broken:
            print(f"   {login:25s} {full_name}")

    await engine.dispose()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Диагностика причин сбоя входа")
    p.add_argument("--apply", action="store_true",
                    help="сбросить пароль найденным битым аккаунтам (иначе только отчёт)")
    args = p.parse_args()
    asyncio.run(main(args.apply))
