"""Сервис аутентификации — JWT."""
import re
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings
from app.database import get_db
from app.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


def hash_password(password: str) -> str:
    # .strip() — пароли в этой системе почти всегда переносятся человеку
    # копипастом через мессенджер/на словах (см. reset_user_password),
    # где случайный завершающий пробел/перенос строки при выделении текста
    # — обычное дело. Отбрасываем его на обоих концах (создание и
    # verify_password ниже), иначе такой хвост навсегда "зашивается" в хэш
    # и человек с виду верным паролем в аккаунт войти не может.
    return pwd_context.hash(password.strip())


_BCRYPT_HASH_RE = re.compile(r"^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$")


def verify_password(plain: str, hashed: str) -> bool:
    """Проверка пароля — поддерживает хэши от passlib ($2b$) и pgcrypto ($2a$).

    Битый/усечённый хэш в БД (следы ad-hoc SQL за долгую историю правок)
    не должен ронять запрос: bcrypt.checkpw — это Rust-реализация, и на
    некорректном вводе она может упасть pyo3_runtime.PanicException, а это
    BaseException, не Exception — обычный except Exception его не ловит,
    и такой сбой на одном-единственном битом аккаунте валит обработку
    запроса целиком (подозреваемая причина массовых жалоб на вход).
    Поэтому: формат хэша проверяем заранее, а на сам вызов всё равно
    держим самый широкий except на случай других сюрпризов рантайма.
    """
    if not hashed or not isinstance(hashed, str):
        return False
    if plain:
        plain = plain.strip()
    try:
        return pwd_context.verify(plain, hashed)
    except ValueError:
        pass
    except Exception:
        return False
    # Fallback: прямой bcrypt для хэшей из pgcrypto (crypt/gen_salt)
    if not _BCRYPT_HASH_RE.match(hashed):
        return False
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except BaseException:
        return False


def create_access_token(user_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),  # исправлено: нормальная DI
):
    return await _get_user(credentials.credentials, db)


async def _get_user(token: str, db: AsyncSession) -> User:
    try:
        payload = decode_access_token(token)
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Недействительный токен")
    except JWTError:
        raise HTTPException(status_code=401, detail="Недействительный токен")

    result = await db.execute(select(User).where(User.id == user_id, User.is_active))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    return user
