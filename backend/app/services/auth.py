"""Сервис аутентификации — JWT."""
import re
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from jwt.exceptions import PyJWTError
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException
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


MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 72  # bcrypt учитывает только первые 72 байта — длиннее бессмысленно и опасно

# Логины в этой системе — транслитерация ФИО, поэтому самый вероятный слабый
# пароль — «то же самое, что логин» или очевидная заготовка. Полный словарь
# не тянем (для полевых пользователей важнее не заблокировать вход), но
# самые тривиальные заготовки отсекаем.
_COMMON_PASSWORDS = frozenset({
    "password", "пароль", "пароль123", "qwerty", "qwerty123", "qwerty1234",
    "12345678", "123456789", "1234567890", "11111111", "abcdefgh",
    "admin123", "adminadmin", "letmein", "iloveyou", "dragon123",
})


def validate_password_strength(password: str, login: str | None = None) -> str | None:
    """Проверка стойкости пароля; возвращает текст ошибки или None, если ок.

    Сознательно не требует спецсимволы: пароли вводят на телефонах в поле, и
    жёсткая политика порождает «P@ssw0rd1» на стикерах. Вместо этого — длина
    (NIST: длина важнее сложности), запрет совпадения с логином и отсев
    тривиальных заготовок.
    """
    pw = password.strip()
    if len(pw) < MIN_PASSWORD_LENGTH:
        return f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов"
    if len(pw) > MAX_PASSWORD_LENGTH:
        return f"Пароль должен быть не длиннее {MAX_PASSWORD_LENGTH} символов"
    if login and pw.lower() == login.strip().lower():
        return "Пароль не должен совпадать с логином"
    if pw.lower() in _COMMON_PASSWORDS:
        return "Слишком простой пароль — выберите другой"
    has_letter = any(ch.isalpha() for ch in pw)
    has_digit = any(ch.isdigit() for ch in pw)
    if len(pw) < 12 and not (has_letter and has_digit):
        return "Короткий пароль должен содержать и буквы, и цифры (или увеличьте длину до 12 символов)"
    return None


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
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Недействительный токен")

    result = await db.execute(select(User).where(User.id == user_id, User.is_active))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    return user
