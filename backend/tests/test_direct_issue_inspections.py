"""Direct issues are the sole source of violations for new inspections."""

import os
import uuid
from datetime import datetime, timedelta

import psycopg2
import pytest
from httpx import AsyncClient

from app.services.timezone import MSK


SYNC_DB_URL = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")


def _exec(sql: str, params=None) -> None:
    with psycopg2.connect(SYNC_DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or {})


def _query_one(sql: str, params=None):
    with psycopg2.connect(SYNC_DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or {})
            return cursor.fetchone()


# Тот же сид-шаблон, что используют тесты обходов (test_review_workflow_
# integrity.py) — привязан к типу площадки "Детская площадка", как и сайты
# из _create_site ниже.
TEMPLATE_ID = "c0000000-0000-0000-0000-000000000001"


async def _create_site(client: AsyncClient, admin_headers: dict[str, str]) -> str:
    me = await client.get("/api/v1/auth/me", headers=admin_headers)
    user_id = me.json()["id"]
    district_id, courtyard_id, site_id = [str(uuid.uuid4()) for _ in range(3)]
    _exec(
        "INSERT INTO districts(id,name,code) VALUES (%(district)s,%(name)s,%(code)s);"
        "INSERT INTO courtyards(id,district_id,name) VALUES (%(courtyard)s,%(district)s,'Тестовый двор');"
        "INSERT INTO sites(id,courtyard_id,type,area_m2,geometry,is_active,assigned_inspector_id) VALUES "
        "(%(site)s,%(courtyard)s,'Детская площадка',100,ST_GeomFromText("
        "'POLYGON((37 55,37.01 55,37.01 55.01,37 55.01,37 55))',4326),true,%(user)s)",
        {"district": district_id, "name": f"Direct {district_id[:8]}", "code": district_id[:8],
         "courtyard": courtyard_id, "site": site_id, "user": user_id},
    )
    return site_id


@pytest.mark.asyncio
async def test_new_issue_requires_an_active_category(client: AsyncClient, admin_headers):
    site_id = await _create_site(client, admin_headers)
    inspection = await client.post("/api/v1/inspections/", json={"site_id": site_id}, headers=admin_headers)
    assert inspection.status_code == 200, inspection.text

    missing_category = await client.post("/api/v1/issues/", json={
        "inspection_id": inspection.json()["id"], "title": "Трещина покрытия", "criticality": "medium",
    }, headers=admin_headers)
    assert missing_category.status_code == 422

    category = (await client.get("/api/v1/issues/categories", headers=admin_headers)).json()[0]
    _exec("UPDATE issue_categories SET is_active=false WHERE id=%(id)s", {"id": category["id"]})
    try:
        inactive_category = await client.post("/api/v1/issues/", json={
            "inspection_id": inspection.json()["id"], "category_id": category["id"],
            "title": "Трещина покрытия", "criticality": "medium",
        }, headers=admin_headers)
        assert inactive_category.status_code == 400
        assert inactive_category.json()["detail"] == "Категория неактивна"
    finally:
        _exec("UPDATE issue_categories SET is_active=true WHERE id=%(id)s", {"id": category["id"]})


@pytest.mark.asyncio
async def test_completion_status_is_derived_from_direct_issues(client: AsyncClient, admin_headers):
    site_id = await _create_site(client, admin_headers)
    inspection = await client.post("/api/v1/inspections/", json={"site_id": site_id}, headers=admin_headers)
    assert inspection.status_code == 200, inspection.text
    inspection_id = inspection.json()["id"]
    category = (await client.get("/api/v1/issues/categories", headers=admin_headers)).json()[0]

    issue = await client.post("/api/v1/issues/", json={
        "inspection_id": inspection_id, "category_id": category["id"],
        "title": "Трещина покрытия", "criticality": "medium",
    }, headers=admin_headers)
    assert issue.status_code == 200, issue.text

    completed = await client.patch(
        f"/api/v1/inspections/{inspection_id}", json={"status": "completed"}, headers=admin_headers,
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "issues_found"


@pytest.mark.asyncio
async def test_new_issue_gets_a_due_date_by_criticality(client: AsyncClient, admin_headers):
    """due_date раньше не проставлялся ни на одном пути создания — оставался
    NULL, и вся "просрочка" (явно исключающая NULL) молча никогда не
    срабатывала. Регрессия на срок по умолчанию: created_at (МСК) + SLA."""
    site_id = await _create_site(client, admin_headers)
    inspection = await client.post("/api/v1/inspections/", json={"site_id": site_id}, headers=admin_headers)
    assert inspection.status_code == 200, inspection.text
    inspection_id = inspection.json()["id"]
    category = (await client.get("/api/v1/issues/categories", headers=admin_headers)).json()[0]

    today_msk = datetime.now(MSK).date()
    for criticality, sla_days in (("critical", 1), ("high", 3), ("medium", 7), ("low", 14)):
        created = await client.post("/api/v1/issues/", json={
            "inspection_id": inspection_id, "category_id": category["id"],
            "title": f"Замечание {criticality}", "criticality": criticality,
        }, headers=admin_headers)
        assert created.status_code == 200, created.text
        assert created.json()["due_date"] == str(today_msk + timedelta(days=sla_days)), criticality


@pytest.mark.asyncio
async def test_checklist_defect_issue_also_gets_a_due_date(client: AsyncClient, admin_headers):
    """Второй путь создания замечания (автоматически из дефекта чек-листа,
    inspections.py) должен получать срок так же, как и ручное создание —
    та же криничность-к-дням функция (default_due_date), не своя копия."""
    site_id = await _create_site(client, admin_headers)
    item_id, is_critical = _query_one(
        "SELECT id, is_critical FROM checklist_items WHERE template_id = %(t)s "
        "AND requires_photo = FALSE ORDER BY sort_order LIMIT 1",
        {"t": TEMPLATE_ID},
    )

    inspection = await client.post("/api/v1/inspections/", json={"site_id": site_id}, headers=admin_headers)
    assert inspection.status_code == 200, inspection.text
    inspection_id = inspection.json()["id"]

    today_msk = datetime.now(MSK).date()
    completed = await client.patch(
        f"/api/v1/inspections/{inspection_id}",
        json={"status": "completed", "answers": [{"checklist_item_id": str(item_id), "result": "defect"}]},
        headers=admin_headers,
    )
    assert completed.status_code == 200, completed.text

    issues = await client.get("/api/v1/issues/", params={"inspection_id": inspection_id}, headers=admin_headers)
    assert issues.status_code == 200, issues.text
    items = issues.json()["items"]
    assert len(items) == 1
    expected_days = 3 if is_critical else 7
    assert items[0]["due_date"] == str(today_msk + timedelta(days=expected_days))


@pytest.mark.asyncio
async def test_maf_issue_gets_at_most_3day_due_date(client: AsyncClient, admin_headers):
    """Поручение со штаба: МАФ устраняется не дольше чем за 3 дня — даже
    если формальная критичность мягче (CATEGORY_SLA_DAYS в
    app/services/issues.py — потолок поверх ISSUE_SLA_DAYS). Без этого
    правила "medium"/"low" по МАФ получили бы 7/14 дней вместо 3.
    "critical" остаётся строже (1 день) — категория не ослабляет срок."""
    site_id = await _create_site(client, admin_headers)
    inspection = await client.post("/api/v1/inspections/", json={"site_id": site_id}, headers=admin_headers)
    assert inspection.status_code == 200, inspection.text
    inspection_id = inspection.json()["id"]

    categories = (await client.get("/api/v1/issues/categories", headers=admin_headers)).json()
    maf_category = next(c for c in categories if c["name"] == "МАФ")

    today_msk = datetime.now(MSK).date()
    for criticality in ("critical", "high", "medium", "low"):
        created = await client.post("/api/v1/issues/", json={
            "inspection_id": inspection_id, "category_id": maf_category["id"],
            "title": f"МАФ, критичность {criticality}", "criticality": criticality,
        }, headers=admin_headers)
        assert created.status_code == 200, created.text
        expected_days = 3 if criticality != "critical" else 1  # critical=1 день короче штабного правила, оставляем как есть
        assert created.json()["due_date"] == str(today_msk + timedelta(days=expected_days)), criticality


@pytest.mark.asyncio
async def test_checklist_maf_defect_gets_3day_due_date_even_if_not_critical(client: AsyncClient, admin_headers):
    """Тот же штабной срок — и для дефекта, автосозданного из некритичного
    пункта чек-листа категории МАФ (без правила получил бы 7 дней, а не 3,
    как остальные некритичные категории)."""
    site_id = await _create_site(client, admin_headers)
    item_id, is_critical = _query_one(
        "SELECT id, is_critical FROM checklist_items WHERE template_id = %(t)s "
        "AND category = 'МАФ' AND is_critical = FALSE ORDER BY sort_order LIMIT 1",
        {"t": TEMPLATE_ID},
    )
    assert not is_critical  # сид-данные это гарантируют, но явная проверка честнее допущения в комментарии

    inspection = await client.post("/api/v1/inspections/", json={"site_id": site_id}, headers=admin_headers)
    assert inspection.status_code == 200, inspection.text
    inspection_id = inspection.json()["id"]

    today_msk = datetime.now(MSK).date()
    completed = await client.patch(
        f"/api/v1/inspections/{inspection_id}",
        json={"status": "completed", "answers": [{"checklist_item_id": str(item_id), "result": "defect"}]},
        headers=admin_headers,
    )
    assert completed.status_code == 200, completed.text

    issues = await client.get("/api/v1/issues/", params={"inspection_id": inspection_id}, headers=admin_headers)
    assert issues.status_code == 200, issues.text
    items = issues.json()["items"]
    assert len(items) == 1
    assert items[0]["due_date"] == str(today_msk + timedelta(days=3))
