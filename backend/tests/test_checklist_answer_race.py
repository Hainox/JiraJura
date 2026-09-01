"""Регрессия: конкурентные PATCH /inspections/{id} для одного и того же
пункта чек-листа (двойной тап "Сохранить" / повтор после таймаута на плохой
связи в поле) не должны падать 500 на UNIQUE(inspection_id,
checklist_item_id) — см. app/routers/inspections.py: update_inspection,
SAVEPOINT вокруг вставки нового ChecklistAnswer."""
import asyncio
import os
import uuid

import psycopg2
import pytest
from httpx import AsyncClient

SYNC_DB_URL = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")

# Сидовый шаблон чек-листа детской площадки — используется так же в
# test_dashboard_statistics.py.
CHILD_TEMPLATE_ID = "c0000000-0000-0000-0000-000000000001"


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


@pytest.mark.asyncio
async def test_concurrent_same_item_patch_does_not_500(client: AsyncClient, admin_headers):
    district_id = (await client.get("/api/v1/districts/", headers=admin_headers)).json()[0]["id"]

    court_id, site_id = str(uuid.uuid4()), str(uuid.uuid4())
    _exec(
        "INSERT INTO courtyards (id, district_id, name) VALUES (%(c)s, %(d)s, %(n)s)",
        {"c": court_id, "d": district_id, "n": "Двор для теста гонки состояний"},
    )
    _exec(
        "INSERT INTO sites (id, courtyard_id, type, area_m2, geometry, is_active) VALUES "
        "(%(s)s, %(c)s, 'Детская площадка', 100, "
        "ST_GeomFromText('POLYGON((46.0 55.8,46.001 55.8,46.001 55.801,46.0 55.801,46.0 55.8))', 4326), true)",
        {"s": site_id, "c": court_id},
    )

    invite = await client.post("/api/v1/auth/invites", json={
        "login": "RaceConditionInspector", "full_name": "Инспектор Гонка Состояний",
        "role": "inspector", "district_id": district_id,
    }, headers=admin_headers)
    assert invite.status_code == 200, invite.text
    complete = await client.post(
        f"/api/v1/auth/invites/{invite.json()['token']}/complete", json={"password": "RaceCond12345"},
    )
    assert complete.status_code == 200, complete.text
    inspector_headers = {"Authorization": f"Bearer {complete.json()['access_token']}"}

    start = await client.post("/api/v1/inspections/", json={"site_id": site_id, "type": "regular"}, headers=inspector_headers)
    assert start.status_code == 200, start.text
    inspection_id = start.json()["id"]

    items = _query_all(
        "SELECT id FROM checklist_items WHERE template_id = %(t)s AND requires_photo = FALSE ORDER BY sort_order LIMIT 1",
        {"t": CHILD_TEMPLATE_ID},
    )
    assert items, "нет пунктов чек-листа без requires_photo для теста"
    item_id = str(items[0][0])

    # asyncio.gather не гарантирует, что оба запроса реально столкнутся в
    # окне SELECT-затем-INSERT (если первый успевает закоммититься раньше,
    # чем второй доходит до своего SELECT, оба просто идут по обычному
    # UPDATE-пути, и тест ничего не говорит про SAVEPOINT-восстановление).
    # Сам механизм восстановления после IntegrityError отдельно и
    # детерминированно проверен на sqlite (см. коммит) до того, как писать
    # эту async-версию — здесь же не хотим городить внутренние тестовые
    # хуки поверх продакшн-кода ради принудительной синхронизации (в этом
    # наборе тестов всё идёт через HTTP-клиент, ни один тест не дёргает
    # роутеры напрямую). Поэтому вместо двух запросов — сразу пять
    # одинаковых: C(5,2)=10 попарных окон гонки вместо одного заметно
    # снижают шанс, что ни одна пара не столкнётся хотя бы на части
    # прогонов CI. Проверяемый инвариант (ни один 500, ровно одна строка в
    # БД) верен независимо от того, сколько пар реально столкнулось.
    payload = {"answers": [{"checklist_item_id": item_id, "result": "ok"}]}
    responses = await asyncio.gather(*(
        client.patch(f"/api/v1/inspections/{inspection_id}", json=payload, headers=inspector_headers)
        for _ in range(5)
    ))
    for r in responses:
        assert r.status_code == 200, r.text

    rows = _query_all(
        "SELECT result FROM checklist_answers WHERE inspection_id = %(i)s AND checklist_item_id = %(c)s",
        {"i": inspection_id, "c": item_id},
    )
    assert len(rows) == 1, f"ожидалась ровно одна строка ответа, получено {len(rows)}"
    assert rows[0][0] == "ok"
