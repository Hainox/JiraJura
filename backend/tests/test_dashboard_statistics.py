"""Регрессия: дашборд считает охват (проверено/не проверено площадок) и
результат обходов (без/с нарушениями), а не только дефекты/замечания —
«зелёные» обходы больше не теряются, а дефект виден сразу в момент обхода,
не дожидаясь, пока прикрепят фото исправления и закроют замечание."""
import os
import uuid

import psycopg2
import pytest
from httpx import AsyncClient

SYNC_DB_URL = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")


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
    """Изолированный район на каждый тест — общая тестовая БД сессии
    переживает отдельные тесты, поэтому считать total_sites по общему
    district[0] нельзя (туда вставляют и другие тесты)."""
    did = str(uuid.uuid4())
    _exec(
        "INSERT INTO districts (id, name, code) VALUES (%(id)s, %(name)s, %(code)s)",
        {"id": did, "name": f"Статистика {suffix}", "code": f"stat_{suffix}"},
    )
    return did


def _site(did: str, court_suffix: str, site_suffix: str, lon: float) -> tuple[str, str]:
    court_id = str(uuid.uuid4())
    site_id = str(uuid.uuid4())
    _exec(
        "INSERT INTO courtyards (id, district_id, name) VALUES (%(c)s, %(d)s, %(n)s)",
        {"c": court_id, "d": did, "n": f"Двор {court_suffix}"},
    )
    _exec(
        "INSERT INTO sites (id, courtyard_id, type, area_m2, geometry, is_active) VALUES "
        "(%(s)s, %(c)s, 'Детская площадка', 100, "
        "ST_GeomFromText('POLYGON((%(lon)s 55.8,%(lon2)s 55.8,%(lon2)s 55.801,%(lon)s 55.801,%(lon)s 55.8))', 4326), true)",
        {"s": site_id, "c": court_id, "lon": lon, "lon2": lon + 0.001},
    )
    return court_id, site_id


@pytest.mark.asyncio
async def test_dashboard_counts_coverage_and_outcome(client: AsyncClient, admin_headers):
    did = _new_district("охват")
    _, site_a = _site(did, "А всё в порядке", "А", 37.5)
    _, site_b = _site(did, "Б с дефектом", "Б", 37.6)

    invite = await client.post("/api/v1/auth/invites", json={
        "login": "DashStatInspector", "full_name": "Статистиков Дашборд",
        "role": "inspector", "district_id": did,
    }, headers=admin_headers)
    assert invite.status_code == 200, invite.text
    complete = await client.post(
        f"/api/v1/auth/invites/{invite.json()['token']}/complete",
        json={"password": "DashStat123"},
    )
    inspector_headers = {"Authorization": f"Bearer {complete.json()['access_token']}"}

    # Пункты чек-листа детской площадки БЕЗ requires_photo (фото-пункт
    # пропускаем — иначе завершение потребовало бы прикрепить фото).
    items = _query_all(
        "SELECT id FROM checklist_items "
        "WHERE template_id = 'c0000000-0000-0000-0000-000000000001' "
        "AND requires_photo = FALSE ORDER BY sort_order"
    )
    assert len(items) >= 2
    item_ok_id, item_defect_id = str(items[0][0]), str(items[1][0])

    # Обход А — полностью «зелёный».
    a = await client.post(
        "/api/v1/inspections/", json={"site_id": site_a, "type": "regular"}, headers=inspector_headers
    )
    assert a.status_code == 200, a.text
    done_a = await client.patch(
        f"/api/v1/inspections/{a.json()['id']}",
        json={"status": "completed", "answers": [{"checklist_item_id": item_ok_id, "result": "ok"}]},
        headers=inspector_headers,
    )
    assert done_a.status_code == 200, done_a.text

    # Обход Б — с дефектом (автоматически рождается замечание).
    b = await client.post(
        "/api/v1/inspections/", json={"site_id": site_b, "type": "regular"}, headers=inspector_headers
    )
    assert b.status_code == 200, b.text
    done_b = await client.patch(
        f"/api/v1/inspections/{b.json()['id']}",
        json={"status": "issues_found", "answers": [
            {"checklist_item_id": item_defect_id, "result": "defect", "comment": "мусор"}
        ]},
        headers=inspector_headers,
    )
    assert done_b.status_code == 200, done_b.text

    dash = await client.get(
        "/api/v1/reports/dashboard", params={"district_id": did}, headers=admin_headers
    )
    assert dash.status_code == 200, dash.text
    totals = dash.json()["totals"]

    assert totals["total_sites"] == 2
    # Обе площадки обойдены — «зелёный» обход учтён в охвате, а не потерян.
    assert totals["sites_inspected"] == 2
    assert totals["sites_not_inspected"] == 0
    # Результат: один обход без нарушений, один с нарушениями.
    assert totals["inspections_ok"] == 1
    assert totals["inspections_with_defects"] == 1
    # Дефект виден сразу, а не только после закрытия замечания.
    assert totals["checklist_defects"] == 1
    assert totals["issues_total"] == 1
    assert totals["issues_open"] == 1


@pytest.mark.asyncio
async def test_dashboard_sites_not_inspected(client: AsyncClient, admin_headers):
    """Площадка без обхода попадает в «не проверено»."""
    did = _new_district("непроверено")
    _site(did, "без обхода", "Б", 37.7)

    dash = await client.get(
        "/api/v1/reports/dashboard", params={"district_id": did}, headers=admin_headers
    )
    totals = dash.json()["totals"]
    assert totals["total_sites"] == 1
    assert totals["sites_inspected"] == 0
    assert totals["sites_not_inspected"] == 1
