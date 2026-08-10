"""Общая инфраструктура для E2E-тестов: поднимает отдельную тестовую БД
(пересоздаётся и мигрируется один раз на сессию тестов), даёт клиент
приложения (httpx + ASGITransport, без реального сетевого порта) и токен
администратора из seed.sql.

DATABASE_URL переопределяется до импорта app.* — engine в app/database.py
создаётся при импорте модуля, поэтому переменная окружения должна быть
выставлена раньше первого `from app...` где-либо в тестах.
"""
import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/jirajura_test",
)
os.environ["DATABASE_URL"] = TEST_DB_URL

import psycopg2
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url

ADMIN_LOGIN = "admin"
ADMIN_PASSWORD = "admin123"


def _run_psql_admin(sql: str) -> None:
    """DROP/CREATE DATABASE не работают внутри транзакции — отдельное
    autocommit-соединение к обслуживающей БД 'postgres', не к тестовой."""
    url = make_url(TEST_DB_URL)
    conn = psycopg2.connect(
        host=url.host, port=url.port or 5432, user=url.username,
        password=url.password, dbname="postgres",
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
    finally:
        conn.close()


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database():
    url = make_url(TEST_DB_URL)
    dbname = url.database
    _run_psql_admin(f'DROP DATABASE IF EXISTS "{dbname}"')
    _run_psql_admin(f'CREATE DATABASE "{dbname}"')

    sync_url = TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(sync_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    finally:
        conn.close()

    env = os.environ.copy()
    env["DATABASE_URL"] = TEST_DB_URL
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR), env=env, check=True,
    )

    seed_sql = (BACKEND_DIR / "seed.sql").read_text()
    conn = psycopg2.connect(sync_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(seed_sql)
    finally:
        conn.close()

    yield


@pytest_asyncio.fixture
async def client():
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    # app.database.engine — процесс-глобальный синглтон, его пул соединений
    # asyncpg привязывается к event loop'у первого теста, что его использовал.
    # pytest-asyncio даёт каждому тесту свой loop (function-scope по
    # умолчанию), поэтому без явного dispose второй тест в файле падает с
    # "attached to a different loop" — пул закрывшегося loop'а не переживает
    # переход к следующему. Закрываем здесь, чтобы следующий тест открыл
    # соединения заново, уже в своём loop'е.
    from app.database import engine
    await engine.dispose()


@pytest_asyncio.fixture
async def admin_headers(client: AsyncClient):
    r = await client.post("/api/v1/auth/login", json={"login": ADMIN_LOGIN, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
