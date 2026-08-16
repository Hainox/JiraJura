"""Регрессии на rate-limit публичного эндпоинта загрузки вложений обращений."""
import pytest

from app.services.rate_limit import RateLimiter


def test_rate_limiter_rejects_after_max_requests():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    for _ in range(3):
        allowed, _ = limiter.check("ip-1")
        assert allowed
    allowed, retry = limiter.check("ip-1")
    assert not allowed
    assert retry > 0
    # Другой ключ (другой IP) не заблокирован.
    assert limiter.check("ip-2")[0]


def test_rate_limiter_resets_after_window(monkeypatch):
    import app.services.rate_limit as rl

    clock = {"now": 1000.0}
    monkeypatch.setattr(rl.time, "monotonic", lambda: clock["now"])

    limiter = RateLimiter(max_requests=1, window_seconds=60)
    assert limiter.check("ip")[0]
    assert not limiter.check("ip")[0]

    clock["now"] += 61.0  # окно истекло
    assert limiter.check("ip")[0]


def test_rate_limiter_byte_budget():
    limiter = RateLimiter(max_requests=100, window_seconds=60, max_bytes=10)
    assert limiter.consume_bytes("ip", 6)
    assert not limiter.consume_bytes("ip", 5)  # 6 + 5 > 10

    # Исчерпанный байтовый бюджет отклоняет и на уровне check() — не читаем файл зря.
    exhausted = RateLimiter(max_requests=100, window_seconds=60, max_bytes=10)
    assert exhausted.consume_bytes("ip", 10)
    assert not exhausted.check("ip")[0]


@pytest.mark.asyncio
async def test_feedback_upload_rate_limited(client, tmp_path, monkeypatch):
    """После N загрузок с одного IP эндпоинт отвечает 429 с Retry-After."""
    from app.routers import feedback

    monkeypatch.setattr(feedback, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(
        feedback,
        "_upload_limiter",
        RateLimiter(max_requests=3, window_seconds=60, max_bytes=None),
    )

    created = await client.post(
        "/api/v1/feedback/",
        json={"report_type": "app", "message": "Проверка rate-limit вложений"},
    )
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]

    for index in range(3):
        uploaded = await client.post(
            f"/api/v1/feedback/{report_id}/attachments",
            files={"file": (f"photo-{index}.png", b"test-image", "image/png")},
        )
        assert uploaded.status_code == 201, uploaded.text

    rejected = await client.post(
        f"/api/v1/feedback/{report_id}/attachments",
        files={"file": ("photo-4.png", b"test-image", "image/png")},
    )
    assert rejected.status_code == 429, rejected.text
    assert rejected.headers.get("retry-after")


@pytest.mark.asyncio
async def test_feedback_upload_byte_budget(client, tmp_path, monkeypatch):
    """Суммарный объём за окно тоже ограничен, файл-нарушитель удаляется с диска."""
    from app.routers import feedback

    monkeypatch.setattr(feedback, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(
        feedback,
        "_upload_limiter",
        RateLimiter(max_requests=100, window_seconds=60, max_bytes=50),
    )

    created = await client.post(
        "/api/v1/feedback/",
        json={"report_type": "app", "message": "Проверка байтового бюджета"},
    )
    report_id = created.json()["id"]

    uploaded = await client.post(
        f"/api/v1/feedback/{report_id}/attachments",
        files={"file": ("big.txt", b"x" * 100, "text/plain")},
    )
    assert uploaded.status_code == 429, uploaded.text
    assert uploaded.headers.get("retry-after")

    # Файл не остался на диске — очистка отработала.
    feedback_dir = tmp_path / "feedback"
    assert not feedback_dir.exists() or len(list(feedback_dir.iterdir())) == 0
