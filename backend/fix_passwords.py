"""Экстренный сброс паролей — самодостаточный, не импортирует app.models.
Запускать внутри контейнера api:
  docker compose -f docker-compose.prod.yml exec api python fix_passwords.py
"""
import os
import sys

# ── 1. Генерируем хэш ТЕМ ЖЕ методом что и hash_password() в auth.py ──
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEFAULT_PASSWORD = os.getenv("RESET_PASSWORD", "12345678")
password_hash = pwd_context.hash(DEFAULT_PASSWORD)

# ── 2. Проверяем что хэш рабочий (самопроверка) ──
assert pwd_context.verify(DEFAULT_PASSWORD, password_hash), \
    "FATAL: сгенерированный хэш не проходит verify! Что-то не так с passlib/bcrypt."

print(f"[OK] Сгенерирован хэш для пароля '{DEFAULT_PASSWORD}'")
print(f"[OK] Самопроверка: verify прошёл")

# ── 3. Подключаемся к БД ──
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/sao_inspection")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def reset_all():
    async with AsyncSessionLocal() as db:
        # Сначала посмотрим кто в базе
        users_result = await db.execute(
            text("SELECT login, full_name, role, is_active, must_change_password FROM users ORDER BY full_name")
        )
        users = users_result.fetchall()
        print(f"\n[INFO] Найдено пользователей: {len(users)}")
        for u in users:
            print(f"  {u[0]:25s} {u[1]:35s} {u[2]:12s} active={u[3]} must_change={u[4]}")

        # Массовый сброс: ВСЕМ активным (кроме deleted_*) ставим новый хэш и must_change_password
        result = await db.execute(
            text(
                "UPDATE users SET password_hash = :hash, is_active = true, "
                "must_change_password = true WHERE login NOT LIKE 'deleted_%'"
            ),
            {"hash": password_hash},
        )
        await db.commit()
        print(f"\n[DONE] Обновлено строк: {result.rowcount}")

        # ── 4. Проверяем хэш прямо в БД ──
        verify_result = await db.execute(
            text("SELECT login FROM users WHERE login NOT LIKE 'deleted_%' LIMIT 1")
        )
        sample = verify_result.fetchone()
        if sample:
            hash_result = await db.execute(
                text("SELECT password_hash FROM users WHERE login = :login"),
                {"login": sample[0]},
            )
            stored_hash = hash_result.fetchone()[0]
            ok = pwd_context.verify(DEFAULT_PASSWORD, stored_hash)
            status = "[OK] ПАРОЛЬ РАБОТАЕТ!" if ok else "[FAIL] ПАРОЛЬ НЕ ПРОХОДИТ ПРОВЕРКУ!"
            print(f"\n[CHECK] Пользователь {sample[0]}: {status}")
            if not ok:
                print(f"[DEBUG] Сохранённый хэш: {stored_hash[:60]}...")
                print("[DEBUG] Пробую bcrypt напрямую...")
                import bcrypt
                try:
                    if bcrypt.checkpw(DEFAULT_PASSWORD.encode(), stored_hash.encode()):
                        print("[DEBUG] bcrypt.checkpw — OK. Проблема в passlib.verify.")
                        print("[DEBUG] Это баг в passlib — исправляем через bcrypt напрямую.")
                        # Перегенерируем хэши через bcrypt напрямую
                        new_hash = bcrypt.hashpw(DEFAULT_PASSWORD.encode(), bcrypt.gensalt()).decode()
                        await db.execute(
                            text(
                                "UPDATE users SET password_hash = :hash, is_active = true, "
                                "must_change_password = true WHERE login NOT LIKE 'deleted_%'"
                            ),
                            {"hash": new_hash},
                        )
                        await db.commit()
                        # Проверяем ещё раз
                        final_hash = (await db.execute(
                            text("SELECT password_hash FROM users WHERE login = :login"),
                            {"login": sample[0]},
                        )).fetchone()[0]
                        final_ok = bcrypt.checkpw(DEFAULT_PASSWORD.encode(), final_hash.encode())
                        print(f"[FINAL] bcrypt проверка: {'OK' if final_ok else 'FAIL'}")
                    else:
                        print("[DEBUG] bcrypt.checkpw — тоже FAIL. Фундаментальная проблема с bcrypt.")
                except Exception as e:
                    print(f"[DEBUG] bcrypt.checkpw exception: {e}")
        else:
            print("\n[CHECK] Нет пользователей для проверки!")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(reset_all())
