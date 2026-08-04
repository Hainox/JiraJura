"""Сбросить пароли всех пользователей на bcrypt (passlib).

Запуск на сервере:
  docker compose -f docker-compose.prod.yml run --rm api python reset_passwords.py
"""
import asyncio
from app.database import get_db
from app.models import User
from app.services.auth import hash_password
from sqlalchemy import update

DEFAULT_PASSWORD = "12345678"


async def main():
    async for db in get_db():
        h = hash_password(DEFAULT_PASSWORD)
        result = await db.execute(
            update(User).values(password_hash=h, is_active=True)
        )
        await db.commit()
        print(f"Готово: все пользователи активны, пароль = {DEFAULT_PASSWORD}")
        break


if __name__ == "__main__":
    asyncio.run(main())
