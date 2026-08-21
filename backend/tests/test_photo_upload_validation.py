"""Регрессия: загрузка фото в обход/замечание принимала ЛЮБОЕ расширение из
имени файла (safe_ext = ext[:5] без валидации). uploads/ раздаётся наружу
БЕЗ авторизации и с Content-Type по расширению (app.mount("/uploads", ...)
в main.py), поэтому .html/.svg в обходе — это stored-XSS в origin
приложения: любой авторизованный инспектор мог залить исполняемый файл, а
тот, кто откроет прямую ссылку, исполнил бы скрипт с доступом к
localStorage (JWT-токен). Белый список расширений (как в feedback.py)
должен отклонять не-фото с 400, а обычный JPEG пропускать."""
import io
import os

import psycopg2
import pytest
from httpx import AsyncClient
from PIL import Image

_buf = io.BytesIO()
Image.new("RGB", (16, 16), (90, 140, 200)).save(_buf, format="JPEG")
_TINY_JPEG = _buf.getvalue()

SYNC_DB_URL = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")


def _exec(sql, params=None):
    conn = psycopg2.connect(SYNC_DB_URL)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
    finally:
        conn.close()


def _active_category_id() -> str:
    conn = psycopg2.connect(SYNC_DB_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM issue_categories WHERE is_active = true ORDER BY sort_order, name LIMIT 1")
            return str(cur.fetchone()[0])
    finally:
        conn.close()


async def _create_inspection(
    client: AsyncClient, admin_headers, court_id: str, site_id: str, label: str,
) -> str:
    r = await client.get("/api/v1/districts/", headers=admin_headers)
    district_id = r.json()[0]["id"]
    _exec(
        "INSERT INTO courtyards (id, district_id, name) VALUES "
        f"('{court_id}', %(d)s, %(name)s)",
        {"d": district_id, "name": f"Тестовый двор — {label}"},
    )
    _exec(
        "INSERT INTO sites (id, courtyard_id, type, area_m2, geometry, is_active) VALUES "
        f"('{site_id}', '{court_id}', 'Детская площадка', 100, "
        "ST_GeomFromText('POLYGON((37.5 55.8,37.501 55.8,37.501 55.801,37.5 55.801,37.5 55.8))', 4326), true)"
    )
    start = await client.post("/api/v1/inspections/", json={
        "site_id": site_id, "type": "regular",
    }, headers=admin_headers)
    assert start.status_code == 200, start.text
    return start.json()["id"]


@pytest.mark.asyncio
async def test_inspection_photo_rejects_non_image_extension(client: AsyncClient, admin_headers):
    insp_id = await _create_inspection(
        client, admin_headers,
        "77777777-7777-7777-7777-777777777771",
        "77777777-7777-7777-7777-777777777772",
        "фото обхода",
    )

    bad = await client.post(
        f"/api/v1/inspections/{insp_id}/photos",
        files={"file": ("evil.html", b"<script>alert(1)</script>", "text/html")},
        headers=admin_headers,
    )
    assert bad.status_code == 400, bad.text

    good = await client.post(
        f"/api/v1/inspections/{insp_id}/photos",
        files={"file": ("general.jpg", _TINY_JPEG, "image/jpeg")},
        headers=admin_headers,
    )
    assert good.status_code == 200, good.text


@pytest.mark.asyncio
async def test_issue_photo_rejects_non_image_extension(client: AsyncClient, admin_headers):
    insp_id = await _create_inspection(
        client, admin_headers,
        "77777777-7777-7777-7777-777777777773",
        "77777777-7777-7777-7777-777777777774",
        "фото замечания",
    )
    created = await client.post("/api/v1/issues/", json={
        "inspection_id": insp_id, "category_id": _active_category_id(),
        "title": "Тестовое замечание", "criticality": "medium",
    }, headers=admin_headers)
    assert created.status_code == 200, created.text
    issue_id = created.json()["id"]

    bad = await client.post(
        f"/api/v1/issues/{issue_id}/photos",
        files={"file": ("payload.svg", b"<svg onload=alert(1)></svg>", "image/svg+xml")},
        headers=admin_headers,
    )
    assert bad.status_code == 400, bad.text

    good = await client.post(
        f"/api/v1/issues/{issue_id}/photos",
        files={"file": ("issue.jpg", _TINY_JPEG, "image/jpeg")},
        headers=admin_headers,
    )
    assert good.status_code == 200, good.text
