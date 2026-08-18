"""Регрессии на безопасность входа: rate-limit/lockout /login, журнал
успешных и провальных входов, парольная политика и валидация логина."""
import pytest

from app.services.auth import validate_password_strength
from app.services.rate_limit import RateLimiter


# ── unit: парольная политика ──────────────────────────────────

def test_password_strength_rejects_login_match():
    assert validate_password_strength("WeakPassUser", login="WeakPassUser") is not None
    assert validate_password_strength("WEAKPASSUSER", login="weakpassuser") is not None


def test_password_strength_rejects_common_and_short():
    assert validate_password_strength("password") is not None
    assert validate_password_strength("12345678") is not None
    assert validate_password_strength("short") is not None  # < 8


def test_password_strength_requires_digit_or_length():
    # 8 букв без цифры и короче 12 — ошибка; 12 букв — ок (длина вместо сложности)
    assert validate_password_strength("abcdefgh") is not None
    assert validate_password_strength("abcdefghijkl") is None


def test_password_strength_accepts_good():
    assert validate_password_strength("Test12345") is None
    assert validate_password_strength("Test12345", login="SomeLogin") is None


# ── unit: lockout-примитивы RateLimiter ───────────────────────

def test_limiter_record_block_reset(monkeypatch):
    import app.services.rate_limit as rl

    clock = {"now": 1000.0}
    monkeypatch.setattr(rl.time, "monotonic", lambda: clock["now"])

    limiter = RateLimiter(max_requests=3, window_seconds=60)
    assert not limiter.is_blocked("k")
    for _ in range(3):
        limiter.record("k")
    assert limiter.is_blocked("k")

    limiter.reset("k")
    assert not limiter.is_blocked("k")

    for _ in range(3):
        limiter.record("k")
    assert limiter.is_blocked("k")
    clock["now"] += 61.0  # окно истекло — блокировка снялась сама
    assert not limiter.is_blocked("k")


# ── интеграционные тесты ──────────────────────────────────────

@pytest.fixture(autouse=True)
def _fresh_login_limiters(monkeypatch):
    """Каждый тест работает со своими лимитерами, иначе неудачные логины
    копили бы общий per-IP счётчик (все тесты приходят с 127.0.0.1) и
    заблокировали бы admin_headers в соседних тестах."""
    from app.routers import auth

    ip_limiter = RateLimiter(max_requests=10000, window_seconds=60)
    acct_limiter = RateLimiter(max_requests=10000, window_seconds=60)
    monkeypatch.setattr(auth, "_login_ip_limiter", ip_limiter)
    monkeypatch.setattr(auth, "_login_account_limiter", acct_limiter)
    return ip_limiter, acct_limiter


@pytest.mark.asyncio
async def test_login_lockout_by_account(client, _fresh_login_limiters):
    """После N неудач аккаунт блокируется (429 + Retry-After), но другой
    логин с того же IP по-прежнему проходит до проверки пароля (401)."""
    ip_limiter, acct_limiter = _fresh_login_limiters
    ip_limiter.max_requests = 100  # IP не мешает — блокирует именно аккаунт
    acct_limiter.max_requests = 3

    for _ in range(3):
        r = await client.post("/api/v1/auth/login", json={"login": "locked_user", "password": "wrong"})
        assert r.status_code == 401

    r = await client.post("/api/v1/auth/login", json={"login": "locked_user", "password": "wrong"})
    assert r.status_code == 429, r.text
    assert r.headers.get("retry-after")

    r = await client.post("/api/v1/auth/login", json={"login": "other_user", "password": "wrong"})
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_failed_and_successful_login_are_journaled(client, admin_headers):
    r = await client.post("/api/v1/auth/login", json={"login": "ghost_user_xyz", "password": "wrong"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Неверный логин или пароль"

    failed = await client.get("/api/v1/audit/", params={"action": "login_failed"}, headers=admin_headers)
    assert failed.status_code == 200, failed.text
    assert any("ghost_user_xyz" in (i["details"] or "") for i in failed.json()["items"])

    success = await client.get("/api/v1/audit/", params={"action": "login_success"}, headers=admin_headers)
    assert success.status_code == 200, success.text
    assert any(i["details"] and "admin" in i["details"] for i in success.json()["items"])


@pytest.mark.asyncio
async def test_complete_invite_rejects_weak_password(client, admin_headers):
    r = await client.post(
        "/api/v1/auth/invites",
        json={"login": "WeakPassUser", "full_name": "Слаб Паролевич", "role": "inspector"},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    token = r.json()["token"]

    # пароль == логин (без учёта регистра)
    r = await client.post(f"/api/v1/auth/invites/{token}/complete", json={"password": "weakpassuser"})
    assert r.status_code == 400, r.text

    # тривиальный пароль из deny-листа
    r = await client.post(f"/api/v1/auth/invites/{token}/complete", json={"password": "password"})
    assert r.status_code == 400, r.text

    # нормальный пароль проходит (токен при ошибках не расходуется)
    r = await client.post(f"/api/v1/auth/invites/{token}/complete", json={"password": "GoodPass123"})
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_login_history_endpoint_filters(client, admin_headers):
    """GET /audit/logins отдаёт только записи входов, фильтрует по результату,
    логину (частичное совпадение) и IP."""
    # подготовим по одной записи каждого типа: неудачная (несуществующий логин)
    # и успешная (админ из фикстуры admin_headers уже залогинился)
    await client.post("/api/v1/auth/login", json={"login": "history_ghost", "password": "wrong"})

    r = await client.get("/api/v1/audit/logins", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 2
    assert all(i["action"] in ("login_success", "login_failed") for i in body["items"])

    # фильтр по результату
    failed = await client.get("/api/v1/audit/logins", params={"result": "failed"}, headers=admin_headers)
    assert failed.status_code == 200
    assert all(i["action"] == "login_failed" for i in failed.json()["items"])
    assert any("history_ghost" in (i["details"] or "") for i in failed.json()["items"])

    success = await client.get("/api/v1/audit/logins", params={"result": "success"}, headers=admin_headers)
    assert success.status_code == 200
    assert success.json()["total"] >= 1
    assert all(i["action"] == "login_success" for i in success.json()["items"])

    # фильтр по логину — частичное совпадение без учёта регистра
    by_login = await client.get("/api/v1/audit/logins", params={"login": "HISTORY_GHOST"}, headers=admin_headers)
    assert by_login.status_code == 200
    assert by_login.json()["total"] == 1
    assert "history_ghost" in (by_login.json()["items"][0]["details"] or "")

    # фильтр по IP — все записи тестов приходят с testclient (127.0.0.1)
    by_ip = await client.get("/api/v1/audit/logins", params={"ip": "127.0.0"}, headers=admin_headers)
    assert by_ip.status_code == 200
    assert by_ip.json()["total"] >= 2


@pytest.mark.asyncio
async def test_login_history_for_other_user_does_not_500(client, admin_headers):
    """Регрессия: get_login_history строил запрос без selectinload(AuditLog.user),
    поэтому r.user.full_name падал с MissingGreenlet — НО только для чужого
    успешного входа. Для входа самого admin'а объект User уже лежит в
    identity map сессии (загружен зависимостью get_current_user), лениво
    подгружать нечего, и тест на его логине бага не ловил. Здесь логинимся
    ДРУГИМ пользователем — его User в этой сессии ещё нигде не загружен,
    ленивая подгрузка обязана сходить в БД и без eager-load падает."""
    r = await client.get("/api/v1/districts/", headers=admin_headers)
    district_id = r.json()[0]["id"]

    invite = await client.post("/api/v1/auth/invites", json={
        "login": "LoginHistoryOther", "full_name": "Логинов Другой Пользователь",
        "role": "inspector", "district_id": district_id,
    }, headers=admin_headers)
    assert invite.status_code == 200, invite.text
    complete = await client.post(
        f"/api/v1/auth/invites/{invite.json()['token']}/complete", json={"password": "OtherUser12345"},
    )
    assert complete.status_code == 200, complete.text

    # Второй раз тем же логином — реальный login_success с непустым user_id,
    # не совпадающим с admin'ом из admin_headers.
    login2 = await client.post(
        "/api/v1/auth/login", json={"login": "LoginHistoryOther", "password": "OtherUser12345"},
    )
    assert login2.status_code == 200, login2.text

    r = await client.get(
        "/api/v1/audit/logins", params={"login": "LoginHistoryOther"}, headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert any(i["action"] == "login_success" for i in items)
    success_item = next(i for i in items if i["action"] == "login_success")
    assert success_item["user_name"] == "Логинов Другой Пользователь"


@pytest.mark.asyncio
async def test_login_history_requires_admin(client, admin_headers):
    # обычный инспектор не должен видеть историю входов
    r = await client.post(
        "/api/v1/auth/invites",
        json={"login": "HistoryInspector", "full_name": "Истор. Инспектор", "role": "inspector"},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    await client.post(f"/api/v1/auth/invites/{token}/complete", json={"password": "GoodPass123"})

    r = await client.post("/api/v1/auth/login", json={"login": "historyinspector", "password": "GoodPass123"})
    assert r.status_code == 200, r.text
    inspector_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    resp = await client.get("/api/v1/audit/logins", headers=inspector_headers)
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_login_validation_and_normalization(client):
    # слишком короткий логин
    r = await client.post("/api/v1/auth/login", json={"login": "ab", "password": "x"})
    assert r.status_code == 422

    # пустой (только пробелы) логин
    r = await client.post("/api/v1/auth/login", json={"login": "   ", "password": "x"})
    assert r.status_code == 422

    # регистр и пробелы по краям не мешают входу
    r = await client.post("/api/v1/auth/login", json={"login": " ADMIN ", "password": "admin123"})
    assert r.status_code == 200, r.text
