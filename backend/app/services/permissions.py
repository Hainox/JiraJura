"""Проверка прав доступа по ролям.

Ролевая модель (см. README): inspector < reviewer < admin.
- inspector — видит и меняет только свои записи.
- reviewer — видит/меняет записи в своей зоне (district_id задан — только
  свой район; district_id IS NULL — весь округ).
- admin — без ограничений.
"""
from fastapi import Depends, HTTPException

from app.models import User
from app.services.auth import get_current_user


def require_role(*roles: str):
    """FastAPI-зависимость: доступ только пользователям с одной из ролей."""
    async def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(403, "Недостаточно прав")
        return current_user
    return checker


def check_own_or_role(current_user: User, owner_id, *roles: str) -> None:
    """Разрешить, если current_user — владелец записи (owner_id) либо его роль
    входит в roles; иначе поднять 403. Используется внутри обработчика после
    того, как ресурс уже загружен из БД и известен его владелец."""
    if owner_id is not None and str(owner_id) == str(current_user.id):
        return
    if current_user.role in roles:
        return
    raise HTTPException(403, "Нет прав")


def in_district_scope(current_user: User, district_id) -> bool:
    """True, если пользователь видит записи из данного района:
    admin — всегда,
    reviewer/inspector с district_id=NULL — весь округ,
    reviewer/inspector с district_id — только свой район."""
    if current_user.role == "admin":
        return True
    if current_user.role in ("reviewer", "inspector"):
        return current_user.district_id is None or str(current_user.district_id) == str(district_id)
    return False
