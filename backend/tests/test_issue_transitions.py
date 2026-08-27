"""Регрессия: решение админа (closed/revision_needed) финально — увести
замечание из этих статусов куда-либо тоже может только админ, не reviewer.
И: assigned_to проверяется на существование пользователя перед записью,
а не падает 500 на нарушении FK. См. app/routers/issues.py: update_issue."""
import io
import os
import uuid

import psycopg2
import pytest
from httpx import AsyncClient
from PIL import Image

SYNC_DB_URL = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")

_buf = io.BytesIO()
Image.new("RGB", (16, 16), (10, 200, 30)).save(_buf, format="JPEG")
_TINY_JPEG = _buf.getvalue()


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


async def _invite_and_login(client: AsyncClient, admin_headers, login: str, full_name: str,
                             role: str, district_id: str, password: str) -> dict:
    invite = await client.post("/api/v1/auth/invites", json={
        "login": login, "full_name": full_name, "role": role, "district_id": district_id,
    }, headers=admin_headers)
    assert invite.status_code == 200, invite.text
    complete = await client.post(
        f"/api/v1/auth/invites/{invite.json()['token']}/complete", json={"password": password},
    )
    assert complete.status_code == 200, complete.text
    return {"Authorization": f"Bearer {complete.json()['access_token']}"}


async def _new_district_site_issue(client: AsyncClient, admin_headers, suffix: str, lon: float):
    did = str(uuid.uuid4())
    court_id, site_id = str(uuid.uuid4()), str(uuid.uuid4())
    _exec(
        "INSERT INTO districts (id, name, code) VALUES (%(id)s, %(name)s, %(code)s)",
        {"id": did, "name": f"Замечания {suffix}", "code": f"iss_{suffix}"},
    )
    _exec(
        "INSERT INTO courtyards (id, district_id, name) VALUES (%(c)s, %(d)s, %(n)s)",
        {"c": court_id, "d": did, "n": f"Двор {suffix}"},
    )
    _exec(
        "INSERT INTO sites (id, courtyard_id, type, area_m2, geometry, is_active) VALUES "
        "(%(s)s, %(c)s, 'Детская площадка', 100, "
        "ST_GeomFromText('POLYGON((%(lon)s 55.8,%(lon2)s 55.8,%(lon2)s 55.801,%(lon)s 55.801,%(lon)s 55.8))', 4326), true)",
        {"s": site_id, "c": court_id, "lon": lon, "lon2": lon + 0.001},
    )
    start = await client.post("/api/v1/inspections/", json={"site_id": site_id, "type": "regular"}, headers=admin_headers)
    assert start.status_code == 200, start.text
    insp_id = start.json()["id"]

    created = await client.post("/api/v1/issues/", json={
        "inspection_id": insp_id, "category_id": _active_category_id(),
        "title": f"Замечание {suffix}", "criticality": "medium",
    }, headers=admin_headers)
    assert created.status_code == 200, created.text
    return did, created.json()["id"]


async def _mark_fixed(client: AsyncClient, admin_headers, issue_id: str):
    photo = await client.post(
        f"/api/v1/issues/{issue_id}/fix-photos",
        files={"file": ("fix.jpg", _TINY_JPEG, "image/jpeg")},
        headers=admin_headers,
    )
    assert photo.status_code == 200, photo.text
    fixed = await client.put(
        f"/api/v1/issues/{issue_id}",
        json={"status": "fixed", "executor_name": "Тестовый исполнитель"},
        headers=admin_headers,
    )
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["status"] == "fixed"


@pytest.mark.asyncio
async def test_reviewer_cannot_reopen_issue_closed_by_admin(client: AsyncClient, admin_headers):
    did, issue_id = await _new_district_site_issue(client, admin_headers, str(uuid.uuid4())[:8], 38.10)
    await _mark_fixed(client, admin_headers, issue_id)

    closed = await client.put(f"/api/v1/issues/{issue_id}", json={"status": "closed"}, headers=admin_headers)
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"

    reviewer_headers = await _invite_and_login(
        client, admin_headers, "ReopenReviewer", "Реоткрыватель Проверяющий",
        "reviewer", did, "Reopen12345",
    )
    reopen = await client.put(
        f"/api/v1/issues/{issue_id}", json={"status": "open"}, headers=reviewer_headers,
    )
    assert reopen.status_code == 403, reopen.text

    # Админ по-прежнему может, если действительно нужно откатить решение.
    admin_reopen = await client.put(
        f"/api/v1/issues/{issue_id}", json={"status": "open"}, headers=admin_headers,
    )
    assert admin_reopen.status_code == 200, admin_reopen.text


@pytest.mark.asyncio
async def test_assign_issue_to_nonexistent_user_is_rejected(client: AsyncClient, admin_headers):
    _, issue_id = await _new_district_site_issue(client, admin_headers, str(uuid.uuid4())[:8], 38.20)

    bogus = await client.put(
        f"/api/v1/issues/{issue_id}", json={"assigned_to": str(uuid.uuid4())}, headers=admin_headers,
    )
    assert bogus.status_code == 400, bogus.text


@pytest.mark.asyncio
async def test_issue_status_rejects_unknown_value(client: AsyncClient, admin_headers):
    _, issue_id = await _new_district_site_issue(client, admin_headers, str(uuid.uuid4())[:8], 38.30)

    bad = await client.put(
        f"/api/v1/issues/{issue_id}", json={"status": "not_a_real_status"}, headers=admin_headers,
    )
    assert bad.status_code == 422, bad.text


@pytest.mark.asyncio
async def test_reviewer_can_resubmit_issue_returned_for_revision(client: AsyncClient, admin_headers):
    suffix = str(uuid.uuid4())[:8]
    did, issue_id = await _new_district_site_issue(client, admin_headers, suffix, 38.40)
    reviewer_headers = await _invite_and_login(
        client, admin_headers, f"RevisionReviewer{suffix}", "Проверяющий Доработки",
        "reviewer", did, "Revision12345",
    )

    await _mark_fixed(client, admin_headers, issue_id)
    returned = await client.put(
        f"/api/v1/issues/{issue_id}",
        json={"status": "revision_needed", "reviewer_comment": "Требуется дополнительная уборка"},
        headers=admin_headers,
    )
    assert returned.status_code == 200, returned.text

    new_photo = await client.post(
        f"/api/v1/issues/{issue_id}/fix-photos",
        files={"file": ("revision-fix.jpg", _TINY_JPEG, "image/jpeg")},
        headers=reviewer_headers,
    )
    assert new_photo.status_code == 200, new_photo.text

    resubmitted = await client.put(
        f"/api/v1/issues/{issue_id}",
        json={"status": "fixed", "executor_name": "Исполнитель после доработки"},
        headers=reviewer_headers,
    )
    assert resubmitted.status_code == 200, resubmitted.text
    assert resubmitted.json()["status"] == "fixed"
