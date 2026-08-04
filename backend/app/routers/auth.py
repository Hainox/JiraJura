"""Auth router: логин, приглашения на регистрацию, управление пользователями."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, UserInvite
from app.schemas import (
    LoginRequest, TokenResponse, UserOut, UserAdminOut, UserRoleUpdate, PasswordResetOut,
    UserInviteCreate, UserInviteCreated, UserInvitePreview, InviteCompleteRequest,
)
from app.services.auth import (
    verify_password, hash_password, create_access_token, get_current_user,
)
from app.services.permissions import require_role

router = APIRouter()

INVITE_EXPIRY = timedelta(hours=72)
ROLES = ("inspector", "reviewer", "admin")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.login == data.login, User.is_active)
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    token = create_access_token(str(user.id), user.role)
    return TokenResponse(
        access_token=token,
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    if user is None:
        raise HTTPException(status_code=401)
    return UserOut.model_validate(user)


# ── Приглашения на регистрацию (только admin создаёт) ──────────

@router.post("/invites", response_model=UserInviteCreated)
async def create_invite(
    data: UserInviteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    if data.role not in ROLES:
        raise HTTPException(400, f"Роль должна быть одной из {ROLES}")

    existing_login = (await db.execute(
        select(User).where(User.login == data.login)
    )).scalar_one_or_none()
    if existing_login:
        raise HTTPException(409, "Логин уже занят")

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + INVITE_EXPIRY

    invite = UserInvite(
        login=data.login,
        full_name=data.full_name,
        role=data.role,
        district_id=data.district_id,
        token_hash=_hash_token(token),
        created_by=current_user.id,
        expires_at=expires_at,
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    return UserInviteCreated(
        id=invite.id,
        login=invite.login,
        full_name=invite.full_name,
        role=invite.role,
        token=token,
        expires_at=invite.expires_at,
    )


async def _get_valid_invite(token: str, db: AsyncSession) -> UserInvite:
    invite = (await db.execute(
        select(UserInvite).where(UserInvite.token_hash == _hash_token(token))
    )).scalar_one_or_none()
    if not invite:
        raise HTTPException(404, "Приглашение не найдено")
    if invite.used_at is not None:
        raise HTTPException(410, "Приглашение уже использовано")
    expires_at = invite.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(410, "Срок действия приглашения истёк")
    return invite


@router.get("/invites/{token}", response_model=UserInvitePreview)
async def preview_invite(token: str, db: AsyncSession = Depends(get_db)):
    invite = await _get_valid_invite(token, db)
    return UserInvitePreview(full_name=invite.full_name, role=invite.role)


@router.post("/invites/{token}/complete", response_model=TokenResponse)
async def complete_invite(
    token: str,
    data: InviteCompleteRequest,
    db: AsyncSession = Depends(get_db),
):
    invite = await _get_valid_invite(token, db)

    user = User(
        login=invite.login,
        password_hash=hash_password(data.password),
        full_name=invite.full_name,
        role=invite.role,
        district_id=invite.district_id,
        is_active=True,
    )
    db.add(user)
    invite.used_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(str(user.id), user.role)
    return TokenResponse(access_token=access_token, user=UserOut.model_validate(user))


# ── Управление пользователями (только admin) ───────────────────

@router.get("/users", response_model=list[UserAdminOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    rows = (await db.execute(select(User).order_by(User.full_name))).scalars().all()
    return [UserAdminOut.model_validate(u) for u in rows]


@router.patch("/users/{user_id}", response_model=UserAdminOut)
async def update_user(
    user_id: str,
    data: UserRoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Пользователь не найден")

    if data.role is not None:
        if data.role not in ROLES:
            raise HTTPException(400, f"Роль должна быть одной из {ROLES}")
        user.role = data.role
    if data.district_id is not None:
        user.district_id = data.district_id
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.phone is not None:
        user.phone = data.phone

    await db.commit()
    await db.refresh(user)
    return UserAdminOut.model_validate(user)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Удалить пользователя. Нельзя удалить самого себя."""
    if str(current_user.id) == user_id:
        raise HTTPException(400, "Нельзя удалить самого себя")
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    await db.delete(user)
    await db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/reset-password", response_model=PasswordResetOut)
async def reset_user_password(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Сбросить пароль пользователя — генерирует новый случайный пароль."""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Пользователь не найден")

    new_password = secrets.token_urlsafe(10)
    user.password_hash = hash_password(new_password)
    await db.commit()
    return PasswordResetOut(new_password=new_password)
