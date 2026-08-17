"""Регрессия: цепочка инспектор → проверяющий → админ не должна допускать
самопроверки (проверяющий/админ, владеющий обходом, не может сам себя
"проверить") и не должна позволять владельцу-инспектору задним числом
менять чек-лист/статус уже проверенного обхода. См. app/routers/
inspections.py: update_inspection, bulk_accept_inspections."""
import os
import uuid

import psycopg2
import pytest
from httpx import AsyncClient

SYNC_DB_URL = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")

TEMPLATE_ID = "c0000000-0000-0000-0000-000000000001"


def _exec(sql, params=None):
    conn = psycopg2.connect(SYNC_DB_URL)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
    finally:
        conn.close()


def _query_all(sql, params=None):
    conn = psycopg2.connect(SYNC_DB_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
            return cur.fetchall()
    finally:
        conn.close()


def _new_district(suffix: str) -> str:
    did = str(uuid.uuid4())
    _exec(
        "INSERT INTO districts (id, name, code) VALUES (%(id)s, %(name)s, %(code)s)",
        {"id": did, "name": f"Проверка {suffix}", "code": f"rev_{suffix}"},
    )
    return did


def _site(did: str, suffix: str, lon: float) -> str:
    court_id, site_id = str(uuid.uuid4()), str(uuid.uuid4())
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
    return site_id


def _ok_item_id() -> str:
    rows = _query_all(
        "SELECT id FROM checklist_items WHERE template_id = %(t)s "
        "AND requires_photo = FALSE ORDER BY sort_order LIMIT 1",
        {"t": TEMPLATE_ID},
    )
    return str(rows[0][0])


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


@pytest.mark.asyncio
async def test_promoted_reviewer_cannot_self_approve_own_inspection(client: AsyncClient, admin_headers):
    """Инспектор ведёт обход, затем его повышают до reviewer (частый в
    жизни кейс) — открыв СВОЙ ЖЕ старый обход, он не должен иметь
    возможность проставить себе reviewed_by."""
    did = _new_district(str(uuid.uuid4())[:8])
    site_id = _site(did, "самопроверка", 37.10)
    item_id = _ok_item_id()

    headers = await _invite_and_login(
        client, admin_headers, "SelfReviewInsp", "Самопроверов Иван",
        "inspector", did, "SelfRev12345",
    )

    start = await client.post("/api/v1/inspections/", json={"site_id": site_id, "type": "regular"}, headers=headers)
    assert start.status_code == 200, start.text
    insp_id = start.json()["id"]

    done = await client.patch(
        f"/api/v1/inspections/{insp_id}",
        json={"status": "completed", "answers": [{"checklist_item_id": item_id, "result": "ok"}]},
        headers=headers,
    )
    assert done.status_code == 200, done.text
    assert done.json()["reviewed_by"] is None

    # Повышаем инспектора до reviewer (тот же человек, тот же токен по прежнему валиден).
    users = await client.get("/api/v1/auth/users", headers=admin_headers)
    me = next(u for u in users.json() if u["login"].lower() == "selfreviewinsp")
    promote = await client.patch(f"/api/v1/auth/users/{me['id']}", json={"role": "reviewer"}, headers=admin_headers)
    assert promote.status_code == 200, promote.text

    # Тем же токеном (роль в БД уже reviewer) "проверяем" свой же обход.
    self_review = await client.patch(
        f"/api/v1/inspections/{insp_id}",
        json={"status": "completed", "reviewer_comment": "сам себе одобряю"},
        headers=headers,
    )
    assert self_review.status_code == 200, self_review.text
    # Ключевая проверка: несмотря на роль reviewer, отметка "проверено" не
    # проставляется, если владелец обхода — тот же человек.
    assert self_review.json()["reviewed_by"] is None


@pytest.mark.asyncio
async def test_owner_cannot_edit_after_real_review(client: AsyncClient, admin_headers):
    """После того как СТОРОННИЙ проверяющий одобрил обход, владелец-
    инспектор больше не может задним числом поменять ответы/статус."""
    did = _new_district(str(uuid.uuid4())[:8])
    site_id = _site(did, "лок", 37.20)
    item_id = _ok_item_id()

    inspector_headers = await _invite_and_login(
        client, admin_headers, "LockInsp", "Locковый Инспектор",
        "inspector", did, "LockIt12345",
    )
    reviewer_headers = await _invite_and_login(
        client, admin_headers, "LockReviewer", "Locковый Проверяющий",
        "reviewer", did, "LockIt12345",
    )

    start = await client.post("/api/v1/inspections/", json={"site_id": site_id, "type": "regular"}, headers=inspector_headers)
    insp_id = start.json()["id"]
    done = await client.patch(
        f"/api/v1/inspections/{insp_id}",
        json={"status": "completed", "answers": [{"checklist_item_id": item_id, "result": "ok"}]},
        headers=inspector_headers,
    )
    assert done.status_code == 200, done.text

    review = await client.patch(
        f"/api/v1/inspections/{insp_id}",
        json={"status": "completed", "reviewer_comment": "принято"},
        headers=reviewer_headers,
    )
    assert review.status_code == 200, review.text
    assert review.json()["reviewed_by"] is not None

    # Инспектор пытается задним числом изменить свой уже проверенный ответ.
    tamper = await client.patch(
        f"/api/v1/inspections/{insp_id}",
        json={"answers": [{"checklist_item_id": item_id, "result": "defect", "comment": "передумал"}]},
        headers=inspector_headers,
    )
    assert tamper.status_code == 409, tamper.text

    # Комментарий (не answers/status) по-прежнему можно поправить — лочим
    # только чек-лист/статус, не всё подряд.
    comment_only = await client.patch(
        f"/api/v1/inspections/{insp_id}", json={"comment": "уточнение"}, headers=inspector_headers,
    )
    assert comment_only.status_code == 200, comment_only.text


@pytest.mark.asyncio
async def test_return_for_revision_requires_comment_and_reopens_for_review(client: AsyncClient, admin_headers):
    did = _new_district(str(uuid.uuid4())[:8])
    site_id = _site(did, "доработка", 37.30)
    item_id = _ok_item_id()

    inspector_headers = await _invite_and_login(
        client, admin_headers, "RevisionInsp", "Доработочный Инспектор",
        "inspector", did, "RevIt12345",
    )
    reviewer_headers = await _invite_and_login(
        client, admin_headers, "RevisionReviewer", "Доработочный Проверяющий",
        "reviewer", did, "RevIt12345",
    )

    start = await client.post("/api/v1/inspections/", json={"site_id": site_id, "type": "regular"}, headers=inspector_headers)
    insp_id = start.json()["id"]
    await client.patch(
        f"/api/v1/inspections/{insp_id}",
        json={"status": "completed", "answers": [{"checklist_item_id": item_id, "result": "ok"}]},
        headers=inspector_headers,
    )

    # Без комментария — отклоняем.
    no_comment = await client.patch(
        f"/api/v1/inspections/{insp_id}", json={"status": "in_progress"}, headers=reviewer_headers,
    )
    assert no_comment.status_code == 400, no_comment.text

    returned = await client.patch(
        f"/api/v1/inspections/{insp_id}",
        json={"status": "in_progress", "reviewer_comment": "переснимите фото"},
        headers=reviewer_headers,
    )
    assert returned.status_code == 200, returned.text
    # Возврат на доработку — не финальное одобрение: reviewed_by снят.
    assert returned.json()["reviewed_by"] is None

    resubmit = await client.patch(
        f"/api/v1/inspections/{insp_id}",
        json={"status": "completed", "answers": [{"checklist_item_id": item_id, "result": "ok"}]},
        headers=inspector_headers,
    )
    assert resubmit.status_code == 200, resubmit.text
    # Пересдача не заблокирована 409, потому что reviewed_by был снят.
    assert resubmit.json()["reviewed_by"] is None


@pytest.mark.asyncio
async def test_bulk_accept_excludes_own_inspection(client: AsyncClient, admin_headers):
    did = _new_district(str(uuid.uuid4())[:8])
    site_id = _site(did, "bulk-self", 37.40)
    item_id = _ok_item_id()

    reviewer_headers = await _invite_and_login(
        client, admin_headers, "BulkSelfReviewer", "Массовый Самопроверов",
        "reviewer", did, "BulkIt12345",
    )

    start = await client.post("/api/v1/inspections/", json={"site_id": site_id, "type": "regular"}, headers=reviewer_headers)
    insp_id = start.json()["id"]
    done = await client.patch(
        f"/api/v1/inspections/{insp_id}",
        json={"status": "completed", "answers": [{"checklist_item_id": item_id, "result": "ok"}]},
        headers=reviewer_headers,
    )
    assert done.status_code == 200, done.text
    assert done.json()["issues_count"] == 0

    bulk = await client.post(
        "/api/v1/inspections/bulk-accept", json={"ids": [insp_id]}, headers=reviewer_headers,
    )
    assert bulk.status_code == 200, bulk.text
    assert bulk.json()["accepted"] == 0
    assert bulk.json()["skipped"] == 1
