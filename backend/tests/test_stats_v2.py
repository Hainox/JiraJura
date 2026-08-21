from io import BytesIO
import os
import uuid
from datetime import date
from types import SimpleNamespace

import pytest
import psycopg2
from pptx import Presentation
from pptx.util import Inches
from openpyxl import load_workbook
from sqlalchemy import event

from app.services.statistics.definitions import percent
from app.services.statistics.pptx import percentage_color
from app.services.statistics.filters import build_filter
from app.services.statistics.service import StatisticsService

SYNC_DB_URL = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")


def _exec(sql, params=None):
    with psycopg2.connect(SYNC_DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or {})


@pytest.mark.parametrize(
    ("numerator", "denominator", "expected"),
    [(0, 0, 0), (1, 2, 50), (2, 3, 67), (1, 8, 13), (199, 200, 100)],
)
def test_percent_uses_half_up(numerator, denominator, expected):
    assert percent(numerator, denominator) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(49, "E06666"), (50, "F4B183"), (69, "F4B183"),
     (70, "FFD966"), (99, "FFD966"), (100, "63BE7B")],
)
def test_pptx_percentage_color_boundaries(value, expected):
    assert percentage_color(value) == expected


@pytest.mark.asyncio
async def test_stats_contract_and_pptx(client, admin_headers):
    params = {"date_from": "2026-08-18", "date_to": "2026-08-20"}
    dashboard = await client.get("/api/v1/stats/dashboard", params=params, headers=admin_headers)
    assert dashboard.status_code == 200, dashboard.text
    payload = dashboard.json()
    assert payload["methodology"] == "v2"
    assert payload["timezone"] == "Europe/Moscow"
    assert payload["period"] == {"date_from": "2026-08-18", "date_to": "2026-08-20"}
    assert payload["totals"]["inspections_total"] == (
        payload["totals"]["inspections_green"]
        + payload["totals"]["inspections_with_defects"]
    )
    assert payload["totals"]["issues_not_fixed"] == (
        payload["totals"]["issues_found"] - payload["totals"]["issues_closed"]
    )

    dynamics = await client.get("/api/v1/stats/dynamics", params=params, headers=admin_headers)
    assert dynamics.status_code == 200, dynamics.text
    assert [day["date"] for day in dynamics.json()["days"]] == [
        "2026-08-18", "2026-08-19", "2026-08-20"
    ]

    categories = await client.get("/api/v1/stats/categories", params=params, headers=admin_headers)
    assert categories.status_code == 200, categories.text
    assert len(categories.json()["categories"]) == 9
    category_reference = await client.get("/api/v1/issues/categories", headers=admin_headers)
    assert category_reference.status_code == 200, category_reference.text
    assert [row["name"] for row in category_reference.json()][-1] == "Прочее"

    pptx = await client.get("/api/v1/stats/shtab.pptx", params=params, headers=admin_headers)
    assert pptx.status_code == 200, pptx.text
    assert "shtab_2026-08-18_2026-08-20.pptx" in pptx.headers["content-disposition"]
    presentation = Presentation(BytesIO(pptx.content))
    assert len(presentation.slides) == 2
    assert presentation.slide_width == Inches(13.333)
    assert presentation.slide_height == Inches(7.5)
    first_slide_text = "\n".join(shape.text for shape in presentation.slides[0].shapes if hasattr(shape, "text"))
    second_slide_text = "\n".join(shape.text for shape in presentation.slides[1].shapes if hasattr(shape, "text"))
    assert "УПРАВЛЕНИЕ ЖИЛИЩНО-КОММУНАЛЬНОГО ХОЗЯЙСТВА" in first_slide_text
    assert "1.1" in first_slide_text
    assert "1.2" in second_slide_text
    district_table = next(shape.table for shape in presentation.slides[0].shapes if shape.has_table)
    assert len(district_table.rows) == len(payload["districts"]) + 2

    excel = await client.get("/api/v1/reports/export.xlsx", params=params, headers=admin_headers)
    assert excel.status_code == 200, excel.text
    workbook = load_workbook(BytesIO(excel.content), data_only=True)
    summary = workbook["Сводка по районам"]
    assert [cell.value for cell in summary[1]][:13] == [
        "Район", "Площадок", "Проверено", "Охват %", "Обходов",
        "Без нарушений", "С наруш.", "Выявлено", "Устранено",
        "Доработка", "Не устранено", "Просрочено", "Устранение %",
    ]
    excel_by_name = {summary.cell(row, 1).value: summary.cell(row, 2).value
                     for row in range(2, summary.max_row + 1)}
    assert excel_by_name == {
        row["district_name"]: row["total_sites"] for row in payload["districts"]
    }


@pytest.mark.asyncio
async def test_stats_rejects_invalid_or_excessive_period(client, admin_headers):
    reversed_period = await client.get(
        "/api/v1/stats/dashboard",
        params={"date_from": "2026-08-20", "date_to": "2026-08-19"},
        headers=admin_headers,
    )
    assert reversed_period.status_code == 422
    excessive = await client.get(
        "/api/v1/stats/dynamics",
        params={"date_from": "2025-01-01", "date_to": "2026-08-20"},
        headers=admin_headers,
    )
    assert excessive.status_code == 422


@pytest.mark.asyncio
async def test_stats_all_time_is_an_explicit_unbounded_period(client, admin_headers):
    response = await client.get(
        "/api/v1/stats/dashboard", params={"all_time": "true"}, headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["period"]["date_from"] == "2026-06-01"


@pytest.mark.asyncio
async def test_dashboard_uses_completed_at_and_computed_overdue(client, admin_headers):
    me = await client.get("/api/v1/auth/me", headers=admin_headers)
    user_id = me.json()["id"]
    district_id, courtyard_id, site_id, inspection_id = [str(uuid.uuid4()) for _ in range(4)]
    _exec(
        "INSERT INTO districts(id,name,code) VALUES (%(d)s,%(n)s,%(c)s);"
        "INSERT INTO courtyards(id,district_id,name) VALUES (%(y)s,%(d)s,%(yn)s);"
        "INSERT INTO sites(id,courtyard_id,type,area_m2,geometry,is_active) VALUES "
        "(%(s)s,%(y)s,'Детская площадка',100,ST_GeomFromText("
        "'POLYGON((39 55,39.01 55,39.01 55.01,39 55.01,39 55))',4326),true);"
        "INSERT INTO inspections(id,site_id,inspector_id,type,status,created_at,completed_at) VALUES "
        "(%(i)s,%(s)s,%(u)s,'regular','completed','2025-01-01T00:00:00Z','2026-08-19T10:00:00Z');"
        "INSERT INTO issues(inspection_id,site_id,category_id,title,status,due_date,created_by,created_at) VALUES "
        "(%(i)s,%(s)s,(SELECT id FROM issue_categories WHERE name='Прочее'),'Просрочка',"
        "'open','2026-08-18',%(u)s,'2026-08-19T11:00:00Z')",
        {"d": district_id, "n": f"Stats {district_id[:8]}", "c": district_id[:8],
         "y": courtyard_id, "yn": "Двор stats", "s": site_id,
         "i": inspection_id, "u": user_id},
    )
    response = await client.get(
        "/api/v1/stats/dashboard",
        params={"date_from": "2026-08-19", "date_to": "2026-08-19", "district_id": district_id},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    row = response.json()["districts"][0]
    assert row["inspections_total"] == 1
    # An issue without a defect answer is still not a green inspection.
    assert row["inspections_green"] == 0
    assert row["inspections_with_defects"] == 1
    assert row["issues_found"] == 1
    assert row["issues_overdue"] == 1

    # Current inventory coverage excludes a deactivated site, while event
    # metrics still retain the completed inspection for the selected period.
    _exec("UPDATE sites SET is_active=false WHERE id=%(s)s", {"s": site_id})
    inactive_response = await client.get(
        "/api/v1/stats/dashboard",
        params={"date_from": "2026-08-19", "date_to": "2026-08-19", "district_id": district_id},
        headers=admin_headers,
    )
    inactive_row = inactive_response.json()["districts"][0]
    assert inactive_row["total_sites"] == 0
    assert inactive_row["sites_inspected"] == 0
    assert inactive_row["inspections_total"] == 1


@pytest.mark.asyncio
async def test_admin_cannot_use_reviewer_bulk_accept(client, admin_headers):
    response = await client.post(
        "/api/v1/inspections/bulk-accept",
        json={"ids": [str(uuid.uuid4())]},
        headers=admin_headers,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Массовая приёмка — только для проверяющего"


@pytest.mark.asyncio
async def test_dashboard_query_count_does_not_grow_with_districts():
    from app.database import async_session, engine

    statements = []

    def record_statement(*args):
        statements.append(args[2])

    event.listen(engine.sync_engine, "before_cursor_execute", record_statement)
    try:
        async with async_session() as db:
            user = SimpleNamespace(role="admin", district_id=None)
            filters = build_filter(user, date(2026, 8, 18), date(2026, 8, 20), None)
            await StatisticsService(db, filters).dashboard()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record_statement)
        await engine.dispose()

    assert len(statements) == 4
