"""Тесты бэкенда — юнит-тесты без FastAPI app."""
import pytest
from app.services.auth import hash_password, verify_password, create_access_token, decode_access_token
from app.services.permissions import check_own_or_role, require_role, in_district_scope
from app.models import User


class TestPasswordHashing:
    def test_hash_and_verify(self):
        h = hash_password("mypassword")
        assert h.startswith("$2b$")
        assert verify_password("mypassword", h) is True

    def test_wrong_password_fails(self):
        h = hash_password("correct")
        assert verify_password("wrong", h) is False

    def test_bcrypt_fallback_for_pgcrypto_hashes(self):
        """$2a$ хэши от pgcrypto тоже принимаются."""
        import bcrypt
        pg_hash = bcrypt.hashpw(b"oldpassword", bcrypt.gensalt(prefix=b"2a")).decode()
        assert verify_password("oldpassword", pg_hash) is True

    def test_each_call_creates_unique_hash(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2


class TestJWT:
    def test_create_and_decode(self):
        token = create_access_token("user-123", "inspector")
        payload = decode_access_token(token)
        assert payload["sub"] == "user-123"
        assert payload["role"] == "inspector"

    def test_decode_invalid_token(self):
        from jose import JWTError
        with pytest.raises(JWTError):
            decode_access_token("not.a.token")


class TestPermissions:
    def test_check_own_or_role_owner(self):
        """Владелец записи всегда имеет доступ."""
        user = User(id="u1", login="a", password_hash="h", full_name="A", role="inspector", is_active=True)
        check_own_or_role(user, "u1", "admin")  # не должно поднять исключение

    def test_check_own_or_role_admin(self):
        """Админ имеет доступ ко всему."""
        user = User(id="admin1", login="a", password_hash="h", full_name="Admin", role="admin", is_active=True)
        check_own_or_role(user, "someone-else", "admin")

    def test_check_own_or_role_denied(self):
        """Инспектор не может трогать чужое."""
        from fastapi import HTTPException
        user = User(id="u1", login="a", password_hash="h", full_name="A", role="inspector", is_active=True)
        with pytest.raises(HTTPException) as exc:
            check_own_or_role(user, "u2", "admin")
        assert exc.value.status_code == 403

    def test_check_own_or_role_reviewer_can(self):
        """Проверяющий может трогать записи в рамках своей роли."""
        user = User(id="rev1", login="r", password_hash="h", full_name="R", role="reviewer", is_active=True)
        check_own_or_role(user, "u2", "reviewer", "admin")  # не должно поднять

    def test_in_district_scope_admin(self):
        user = User(id="a", login="a", password_hash="h", full_name="A", role="admin", is_active=True)
        assert in_district_scope(user, "any-district") is True

    def test_in_district_scope_reviewer_matches(self):
        user = User(id="r", login="r", password_hash="h", full_name="R", role="reviewer", district_id="d1", is_active=True)
        assert in_district_scope(user, "d1") is True

    def test_in_district_scope_reviewer_mismatch(self):
        user = User(id="r", login="r", password_hash="h", full_name="R", role="reviewer", district_id="d1", is_active=True)
        assert in_district_scope(user, "d2") is False

    def test_in_district_scope_reviewer_whole_district(self):
        """district_id=None → видит весь округ."""
        user = User(id="r", login="r", password_hash="h", full_name="R", role="reviewer", district_id=None, is_active=True)
        assert in_district_scope(user, "any") is True


class TestModels:
    def test_user_creation(self):
        u = User(id="u1", login="test", password_hash="abc", full_name="Тест", role="inspector", is_active=True)
        assert u.login == "test"
        assert u.role == "inspector"
        assert u.is_active is True

    def test_audit_log_model(self):
        from app.models import AuditLog
        a = AuditLog(user_id="u1", action="login", entity_type="user", entity_id="u1", details="{}")
        assert a.action == "login"
        assert a.entity_type == "user"
