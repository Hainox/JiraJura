"""Direct issues are the sole source of violations for new inspections."""

import os
import uuid

import psycopg2
import pytest
from httpx import AsyncClient


SYNC_DB_URL = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")


def _exec(sql: str, params=None) -> None:
    with psycopg2.connect(SYNC_DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or {})


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
    inactive_category = await client.post("/api/v1/issues/", json={
        "inspection_id": inspection.json()["id"], "category_id": category["id"],
        "title": "Трещина покрытия", "criticality": "medium",
    }, headers=admin_headers)
    assert inactive_category.status_code == 400
    assert inactive_category.json()["detail"] == "Категория неактивна"


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
