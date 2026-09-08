"""The map must distinguish today's inspections from historical ones."""

import os
import uuid

import psycopg2
import pytest
from httpx import AsyncClient


SYNC_DB_URL = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")


def _exec(sql: str, params: dict) -> None:
    with psycopg2.connect(SYNC_DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)


@pytest.mark.asyncio
async def test_inspection_list_filters_by_moscow_calendar_day(client: AsyncClient, admin_headers):
    """Yesterday's completed inspection must not mark a site as visited today."""
    admin = await client.get("/api/v1/auth/me", headers=admin_headers)
    assert admin.status_code == 200, admin.text

    district_id, courtyard_id, site_id = [str(uuid.uuid4()) for _ in range(3)]
    yesterday_id, today_id = [str(uuid.uuid4()) for _ in range(2)]
    _exec(
        "INSERT INTO districts (id, name, code) VALUES (%(district)s, 'Календарный тест', %(code)s);"
        "INSERT INTO courtyards (id, district_id, name) VALUES (%(courtyard)s, %(district)s, 'Тестовый двор');"
        "INSERT INTO sites (id, courtyard_id, type, area_m2, geometry, is_active) VALUES "
        "(%(site)s, %(courtyard)s, 'Детская площадка', 100, "
        "ST_GeomFromText('POLYGON((37 55,37.01 55,37.01 55.01,37 55.01,37 55))', 4326), true);"
        "INSERT INTO inspections (id, site_id, inspector_id, type, status, created_at) VALUES "
        "(%(yesterday)s, %(site)s, %(user)s, 'regular', 'completed', '2026-09-07T20:59:59Z'),"
        "(%(today)s, %(site)s, %(user)s, 'regular', 'completed', '2026-09-07T21:00:00Z');",
        {
            "district": district_id,
            "code": f"calendar-{district_id[:8]}",
            "courtyard": courtyard_id,
            "site": site_id,
            "user": admin.json()["id"],
            "yesterday": yesterday_id,
            "today": today_id,
        },
    )

    today = await client.get(
        "/api/v1/inspections/",
        params={"district_id": district_id, "date_from": "2026-09-08", "date_to": "2026-09-08"},
        headers=admin_headers,
    )
    assert today.status_code == 200, today.text
    assert [row["id"] for row in today.json()["items"]] == [today_id]

    yesterday = await client.get(
        "/api/v1/inspections/",
        params={"district_id": district_id, "date_from": "2026-09-07", "date_to": "2026-09-07"},
        headers=admin_headers,
    )
    assert yesterday.status_code == 200, yesterday.text
    assert [row["id"] for row in yesterday.json()["items"]] == [yesterday_id]
