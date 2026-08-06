"""Auth router: логин, приглашения на регистрацию, управление пользователями."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, UserInvite
from app.schemas import (
    LoginRequest, TokenResponse, UserOut, UserAdminOut, UserRoleUpdate, SelfUpdateRequest,
    PasswordResetOut, ChangePasswordRequest,
    UserInviteCreate, UserInviteCreated, UserInvitePreview, InviteCompleteRequest,
)
from app.services.auth import (
    verify_password, hash_password, create_access_token, get_current_user,
)
from app.services.permissions import require_role
from app.services.audit import log_action

router = APIRouter()

INVITE_EXPIRY = timedelta(hours=72)
ROLES = ("inspector", "reviewer", "admin")

# Без 0/O/1/l/I и других визуально похожих символов — этот пароль почти
# всегда передаётся человеку на словах или сообщением в мессенджере
# ("Передайте его пользователю лично"), а не вводится напрямую самим
# сотрудником, поэтому неоднозначные символы — реальный источник ошибок
# при перепечатывании/чтении, а не гипотетический краевой случай.
_PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _gen_readable_password(length: int = 12) -> str:
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    # логин без учёта регистра: логины вида "AbdulloevRM" легко превращаются
    # в "abdulloevrm" из-за автокапитализации/автозамены на телефоне —
    # это не должно приводить к "неверный логин или пароль"
    result = await db.execute(
        select(User).where(func.lower(User.login) == data.login.strip().lower(), User.is_active)
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    token = create_access_token(str(user.id), user.role)
    return TokenResponse(
        access_token=token,
        user=UserOut.model_validate(user),
        must_change_password=bool(user.must_change_password),
    )


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    if user is None:
        raise HTTPException(status_code=401)
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
async def update_me(
    data: SelfUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Самостоятельное редактирование своего профиля (ФИО, телефон) —
    доступно любой роли, в отличие от /users/{id} (только admin, там же
    можно менять role/district_id/is_active)."""
    if data.full_name is not None:
        current_user.full_name = data.full_name
    if data.phone is not None:
        current_user.phone = data.phone
    await db.commit()
    await db.refresh(current_user)
    return UserOut.model_validate(current_user)


# ── Приглашения на регистрацию (только admin создаёт) ──────────

@router.post("/invites", response_model=UserInviteCreated)
async def create_invite(
    data: UserInviteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    if data.role not in ROLES:
        raise HTTPException(400, f"Роль должна быть одной из {ROLES}")

    login_norm = data.login.strip().lower()
    existing_login = (await db.execute(
        select(User.id).where(func.lower(User.login) == login_norm)
    )).scalar_one_or_none()
    if existing_login:
        raise HTTPException(409, "Логин уже занят")

    # login уникален и в user_invites (UNIQUE-constraint в модели) — без этой
    # проверки повторное приглашение уже приглашённого логина падало с 500
    # (IntegrityError) вместо понятного 409. Если прежнее приглашение
    # просрочено и не использовано — перевыпускаем его молча (иначе логин
    # оставался бы заблокирован навсегда после истечения 72 часов). Сравнение
    # без учёта регистра — по той же причине, что и в /login.
    existing_invite = (await db.execute(
        select(UserInvite).where(func.lower(UserInvite.login) == login_norm)
    )).scalar_one_or_none()
    if existing_invite:
        if existing_invite.used_at is not None:
            raise HTTPException(409, "Логин уже занят")
        exp = existing_invite.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp >= datetime.now(timezone.utc):
            raise HTTPException(409, "Логин уже занят: приглашение уже отправлено и ещё активно")
        await db.delete(existing_invite)
        await db.flush()

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
    # invite.id — Python-side default (uuid.uuid4), заполняется только при
    # flush; без него в лог попадала строка "None" вместо реального id
    await db.flush()
    await log_action(db, str(current_user.id), "invite_create", "user_invite", str(invite.id), {"login": data.login, "role": data.role})
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
    # district_id=None — валидное целевое состояние (проверяющий "весь округ"),
    # а не "поле не передано": проверяем model_fields_set, а не is not None,
    # иначе снять район с уже назначенного проверяющего/сделать его
    # округ-wide через этот эндпоинт было бы физически невозможно
    if "district_id" in data.model_fields_set:
        user.district_id = data.district_id
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.phone is not None:
        user.phone = data.phone

    # exclude_unset (не exclude_none!) — иначе явно переданный district_id=null
    # (снятие района) вырезается из лога вместе с полями, которых вовсе не было
    # в запросе, и в аудите остаётся пустая запись вместо реального изменения
    await log_action(db, str(current_user.id), "user_update", "user", user_id, data.model_dump(exclude_unset=True))
    await db.commit()
    await db.refresh(user)
    return UserAdminOut.model_validate(user)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Деактивировать пользователя (софт-делит).

    Реальные записи не удаляются, чтобы не нарушить FK-целостность
    (обходы, замечания, история статусов ссылаются на users.id).
    Пользователь помечается is_active=False, логин заменяется на
    deleted_<id>, чтобы освободить логин для новых приглашений.
    """
    if str(current_user.id) == user_id:
        raise HTTPException(400, "Нельзя удалить самого себя")
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Пользователь не найден")

    await log_action(db, str(current_user.id), "user_delete", "user", user_id, {"login": user.login})

    # Софт-делит: деактивируем и переименовываем логин
    user.is_active = False
    user.login = f"deleted_{user_id[:8]}"
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

    new_password = _gen_readable_password()
    user.password_hash = hash_password(new_password)
    await log_action(db, str(current_user.id), "password_reset", "user", user_id, {"login": user.login})
    await db.commit()
    return PasswordResetOut(new_password=new_password)


@router.post("/change-password", response_model=TokenResponse)
async def change_password(
    data: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Смена пароля (принудительная при первом входе)."""
    current_user.password_hash = hash_password(data.new_password)
    current_user.must_change_password = False
    await db.commit()
    await db.refresh(current_user)

    token = create_access_token(str(current_user.id), current_user.role)
    return TokenResponse(
        access_token=token,
        user=UserOut.model_validate(current_user),
        must_change_password=False,
    )
