"""Журнал осмотра люков: осмотр люков в обходе, замечания по дефектам,
гейт завершения обхода, журнал района/округа и его выгрузка в Excel.

Каждый тест заводит свой район — KPI журнала считаются по зоне видимости,
и данные соседних тестов в общей тестовой БД не должны в них попадать.
"""
import asyncio
import os
import uuid
from datetime import datetime, timedelta
from io import BytesIO

import psycopg2
import pytest
from httpx import AsyncClient
from openpyxl import load_workbook

from app.services.timezone import MSK

SYNC_DB_URL = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
LEGACY_TEMPLATE_ID = "c0000000-0000-0000-0000-000000000001"
JOURNAL_HEADERS = [
    "№", "Дата, время", "Район", "Адрес площадки", "Тип", "Люк / владелец",
    "Состояние", "Фото", "Принятые меры", "Осмотрел", "Устранено",
]


def _exec(sql, params=None):
    with psycopg2.connect(SYNC_DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or {})


def _one(sql, params=None):
    with psycopg2.connect(SYNC_DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or {})
            return cursor.fetchone()


def _new_district() -> str:
    district_id = str(uuid.uuid4())
    _exec(
        "INSERT INTO districts(id,name,code) VALUES (%(d)s,%(n)s,%(c)s)",
        {"d": district_id, "n": f"Люки {district_id[:8]}", "c": district_id[:8]},
    )
    return district_id


def _new_site(district_id: str, name: str = "Тестовый двор", section: str | None = None) -> str:
    courtyard_id, site_id = str(uuid.uuid4()), str(uuid.uuid4())
    _exec(
        "INSERT INTO courtyards(id,district_id,name,section) VALUES (%(c)s,%(d)s,%(n)s,%(s)s);"
        "INSERT INTO sites(id,courtyard_id,type,area_m2,geometry,is_active) VALUES "
        "(%(site)s,%(c)s,'Детская площадка',100,ST_GeomFromText("
        "'POLYGON((37 55,37.01 55,37.01 55.01,37 55.01,37 55))',4326),true)",
        {"c": courtyard_id, "d": district_id, "n": f"{name} {courtyard_id[:6]}", "s": section, "site": site_id},
    )
    return site_id


async def _user(client: AsyncClient, admin_headers, role: str, district_id: str | None) -> tuple[str, dict]:
    login = f"hatch_{role}_{uuid.uuid4().hex[:10]}"
    invite = await client.post("/api/v1/auth/invites", json={
        "login": login, "full_name": f"Люки {role}", "role": role, "district_id": district_id,
    }, headers=admin_headers)
    assert invite.status_code == 200, invite.text
    done = await client.post(
        f"/api/v1/auth/invites/{invite.json()['token']}/complete", json={"password": "HatchTest12345"},
    )
    assert done.status_code == 200, done.text
    payload = done.json()
    return payload["user"]["id"], {"Authorization": f"Bearer {payload['access_token']}"}


async def _hatch(client, admin_headers, site_id, number, owner=None, **extra) -> str:
    created = await client.post("/api/v1/hatches", json={
        "site_id": site_id, "number": number, "owner": owner, **extra,
    }, headers=admin_headers)
    assert created.status_code == 200, created.text
    return created.json()["id"]


async def _start(client, headers, site_id) -> str:
    started = await client.post("/api/v1/inspections/", json={"site_id": site_id}, headers=headers)
    assert started.status_code == 200, started.text
    return started.json()["id"]


async def _put(client, headers, inspection_id, hatch_id, **body):
    return await client.put(
        f"/api/v1/inspections/{inspection_id}/hatches/{hatch_id}", json=body, headers=headers,
    )


async def _photo(client, headers, issue_id):
    r = await client.post(
        f"/api/v1/issues/{issue_id}/photos",
        files={"file": ("hatch.jpg", b"\xff\xd8\xff\xe0fake-jpeg", "image/jpeg")},
        headers=headers,
    )
    assert r.status_code == 200, r.text


def _issue_count(inspection_id) -> int:
    return _one("SELECT count(*) FROM issues WHERE inspection_id=%(i)s", {"i": inspection_id})[0]


@pytest.mark.asyncio
async def test_admin_manages_hatches_of_a_site(client: AsyncClient, admin_headers):
    district_id = _new_district()
    site_id = _new_site(district_id)
    for number in ("10", "2а", "1"):
        await _hatch(client, admin_headers, site_id, number, owner="Мосводоканал")
    hatch_id = await _hatch(client, admin_headers, site_id, "3", lat=55.8, lon=37.5, external_id=f"ext-{site_id}")

    duplicate = await client.post("/api/v1/hatches", json={"site_id": site_id, "number": "1"}, headers=admin_headers)
    assert duplicate.status_code == 409
    duplicate_ext = await client.post(
        "/api/v1/hatches", json={"site_id": site_id, "number": "4", "external_id": f"ext-{site_id}"},
        headers=admin_headers,
    )
    assert duplicate_ext.status_code == 409

    listed = await client.get("/api/v1/hatches", params={"site_id": site_id}, headers=admin_headers)
    assert listed.status_code == 200, listed.text
    assert [h["number"] for h in listed.json()] == ["1", "2а", "3", "10"]
    point = next(h for h in listed.json() if h["id"] == hatch_id)
    assert point["lat"] == pytest.approx(55.8) and point["lon"] == pytest.approx(37.5)

    patched = await client.patch(f"/api/v1/hatches/{hatch_id}", json={
        "owner": "МОЭК", "location_note": "у входа", "is_active": False, "lat": None, "lon": None,
    }, headers=admin_headers)
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert (body["owner"], body["location_note"], body["is_active"], body["lat"]) == ("МОЭК", "у входа", False, None)
    renumber = await client.patch(f"/api/v1/hatches/{hatch_id}", json={"number": "1"}, headers=admin_headers)
    assert renumber.status_code == 409

    _, inspector_headers = await _user(client, admin_headers, "inspector", district_id)
    forbidden = await client.post("/api/v1/hatches", json={"site_id": site_id, "number": "9"}, headers=inspector_headers)
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_defect_creates_exactly_one_critical_issue_due_next_day(client: AsyncClient, admin_headers):
    district_id = _new_district()
    site_id = _new_site(district_id)
    hatch_id = await _hatch(client, admin_headers, site_id, "2", owner="Мосводоканал", location_note="у входа")
    _, inspector_headers = await _user(client, admin_headers, "inspector", district_id)
    inspection_id = await _start(client, inspector_headers, site_id)

    ok = await _put(client, inspector_headers, inspection_id, hatch_id, state="ok")
    assert ok.status_code == 200, ok.text
    assert ok.json()["state"] == "ok" and ok.json()["issue_id"] is None
    assert _issue_count(inspection_id) == 0

    defect = await _put(
        client, inspector_headers, inspection_id, hatch_id,
        state="shifted", fenced=True, owner_ticket=" 55 ", comment="крышка сдвинута",
    )
    assert defect.status_code == 200, defect.text
    issue_id = defect.json()["issue_id"]
    assert issue_id and defect.json()["issue_status"] == "open"
    assert defect.json()["owner_ticket"] == "55"

    issue = (await client.get(f"/api/v1/issues/{issue_id}", headers=admin_headers)).json()
    assert issue["category_name"] == "Люки"
    assert issue["criticality"] == "critical"
    assert issue["inspection_id"] == inspection_id and issue["site_id"] == site_id
    assert issue["due_date"] == str(datetime.now(MSK).date() + timedelta(days=1))
    assert issue["title"] == "Люк №2 · Мосводоканал: Крышка смещена / неплотно закрыта"
    assert "Опасное место ограждено" in issue["description"]
    assert "Заявка владельцу № 55" in issue["description"]
    assert "Расположение: у входа" in issue["description"]

    again = await _put(client, inspector_headers, inspection_id, hatch_id, state="shifted", fenced=True, owner_ticket="55")
    assert again.status_code == 200 and again.json()["issue_id"] == issue_id
    other_defect = await _put(client, inspector_headers, inspection_id, hatch_id, state="missing", fenced=False)
    assert other_defect.json()["issue_id"] == issue_id
    assert _issue_count(inspection_id) == 1
    issue = (await client.get(f"/api/v1/issues/{issue_id}", headers=admin_headers)).json()
    assert issue["title"] == "Люк №2 · Мосводоканал: Крышка отсутствует"
    assert "Опасное место не ограждено" in issue["description"]
    assert _one("SELECT count(*) FROM hatch_checks WHERE inspection_id=%(i)s", {"i": inspection_id})[0] == 1


@pytest.mark.asyncio
async def test_concurrent_defect_puts_create_one_issue(client: AsyncClient, admin_headers):
    district_id = _new_district()
    site_id = _new_site(district_id)
    hatch_id = await _hatch(client, admin_headers, site_id, "1")
    _, inspector_headers = await _user(client, admin_headers, "inspector", district_id)
    inspection_id = await _start(client, inspector_headers, site_id)

    responses = await asyncio.gather(*(
        _put(client, inspector_headers, inspection_id, hatch_id, state="damaged") for _ in range(5)
    ))
    for r in responses:
        assert r.status_code == 200, r.text
    assert len({r.json()["issue_id"] for r in responses}) == 1
    assert _issue_count(inspection_id) == 1


@pytest.mark.asyncio
async def test_put_recovers_when_concurrent_insert_wins_the_race(client: AsyncClient, admin_headers):
    """Детерминированная гонка: чужая транзакция уже вставила осмотр этого
    люка, но ещё не закоммитила — PUT его не видит, упирается в UNIQUE при
    INSERT и должен после коммита конкурента обновить его строку, а не
    упасть 500 (gather выше это окно через ASGITransport не ловит)."""
    district_id = _new_district()
    site_id = _new_site(district_id)
    hatch_id = await _hatch(client, admin_headers, site_id, "1")
    user_id, inspector_headers = await _user(client, admin_headers, "inspector", district_id)
    inspection_id = await _start(client, inspector_headers, site_id)

    competitor = psycopg2.connect(SYNC_DB_URL)
    try:
        with competitor.cursor() as cursor:
            cursor.execute(
                "INSERT INTO hatch_checks(inspection_id,hatch_id,state,checked_by) "
                "VALUES (%(i)s,%(h)s,'ok',%(u)s)",
                {"i": inspection_id, "h": hatch_id, "u": user_id},
            )
        request = asyncio.create_task(_put(client, inspector_headers, inspection_id, hatch_id, state="damaged"))
        await asyncio.sleep(1.0)
        assert not request.done()
        competitor.commit()
        response = await request
    finally:
        competitor.close()

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "damaged" and response.json()["issue_id"]
    assert _one("SELECT count(*) FROM hatch_checks WHERE inspection_id=%(i)s", {"i": inspection_id})[0] == 1
    assert _issue_count(inspection_id) == 1


@pytest.mark.asyncio
async def test_defect_back_to_ok_removes_untouched_issue(client: AsyncClient, admin_headers):
    district_id = _new_district()
    site_id = _new_site(district_id)
    hatch_id = await _hatch(client, admin_headers, site_id, "1")
    _, inspector_headers = await _user(client, admin_headers, "inspector", district_id)
    inspection_id = await _start(client, inspector_headers, site_id)

    defect = await _put(client, inspector_headers, inspection_id, hatch_id, state="sink")
    issue_id = defect.json()["issue_id"]
    await _photo(client, inspector_headers, issue_id)

    back = await _put(client, inspector_headers, inspection_id, hatch_id, state="ok")
    assert back.status_code == 200, back.text
    assert back.json()["issue_id"] is None and back.json()["photos"] == []
    assert _issue_count(inspection_id) == 0
    assert _one("SELECT count(*) FROM photos WHERE issue_id=%(i)s", {"i": issue_id})[0] == 0
    assert (await client.get(f"/api/v1/issues/{issue_id}", headers=admin_headers)).status_code == 404


@pytest.mark.asyncio
async def test_defect_back_to_ok_keeps_issue_already_in_work(client: AsyncClient, admin_headers):
    district_id = _new_district()
    site_id = _new_site(district_id)
    hatch_id = await _hatch(client, admin_headers, site_id, "1")
    _, inspector_headers = await _user(client, admin_headers, "inspector", district_id)
    _, reviewer_headers = await _user(client, admin_headers, "reviewer", district_id)
    inspection_id = await _start(client, inspector_headers, site_id)

    issue_id = (await _put(client, inspector_headers, inspection_id, hatch_id, state="damaged")).json()["issue_id"]
    in_work = await client.put(f"/api/v1/issues/{issue_id}", json={"status": "in_work"}, headers=reviewer_headers)
    assert in_work.status_code == 200, in_work.text

    back = await _put(client, inspector_headers, inspection_id, hatch_id, state="ok")
    assert back.status_code == 200, back.text
    assert back.json()["issue_id"] == issue_id
    assert back.json()["issue_status"] == "in_work"
    assert _issue_count(inspection_id) == 1


@pytest.mark.asyncio
async def test_all_ok_fills_only_unchecked_hatches(client: AsyncClient, admin_headers):
    district_id = _new_district()
    site_id = _new_site(district_id)
    first = await _hatch(client, admin_headers, site_id, "1")
    await _hatch(client, admin_headers, site_id, "2")
    await _hatch(client, admin_headers, site_id, "3")
    inactive = await _hatch(client, admin_headers, site_id, "4")
    await client.patch(f"/api/v1/hatches/{inactive}", json={"is_active": False}, headers=admin_headers)
    _, inspector_headers = await _user(client, admin_headers, "inspector", district_id)
    inspection_id = await _start(client, inspector_headers, site_id)

    await _put(client, inspector_headers, inspection_id, first, state="missing")
    marked = await client.post(f"/api/v1/inspections/{inspection_id}/hatches/all-ok", headers=inspector_headers)
    assert marked.status_code == 200, marked.text
    states = {row["hatch"]["number"]: row["check"]["state"] for row in marked.json()}
    assert states == {"1": "missing", "2": "ok", "3": "ok"}

    again = await client.post(f"/api/v1/inspections/{inspection_id}/hatches/all-ok", headers=inspector_headers)
    assert again.status_code == 200
    assert _one("SELECT count(*) FROM hatch_checks WHERE inspection_id=%(i)s", {"i": inspection_id})[0] == 3
    assert _issue_count(inspection_id) == 1

    inactive_put = await _put(client, inspector_headers, inspection_id, inactive, state="ok")
    assert inactive_put.status_code == 400


@pytest.mark.asyncio
async def test_completion_gate_requires_every_hatch_and_defect_photo(client: AsyncClient, admin_headers):
    district_id = _new_district()
    site_id = _new_site(district_id)
    first = await _hatch(client, admin_headers, site_id, "1")
    await _hatch(client, admin_headers, site_id, "3")
    _, inspector_headers = await _user(client, admin_headers, "inspector", district_id)
    inspection_id = await _start(client, inspector_headers, site_id)

    async def complete():
        return await client.patch(
            f"/api/v1/inspections/{inspection_id}", json={"status": "completed"}, headers=inspector_headers,
        )

    nothing = await complete()
    assert nothing.status_code == 400
    assert nothing.json()["detail"] == "Отметьте люки: №1, №3"

    issue_id = (await _put(client, inspector_headers, inspection_id, first, state="damaged")).json()["issue_id"]
    one_left = await complete()
    assert one_left.status_code == 400
    assert one_left.json()["detail"] == "Отметьте люк №3"

    await client.post(f"/api/v1/inspections/{inspection_id}/hatches/all-ok", headers=inspector_headers)
    no_photo = await complete()
    assert no_photo.status_code == 400
    assert no_photo.json()["detail"] == "Нужно фото для люка №1"
    status = _one("SELECT status FROM inspections WHERE id=%(i)s", {"i": inspection_id})[0]
    assert status == "in_progress"

    await _photo(client, inspector_headers, issue_id)
    done = await complete()
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "critical"


@pytest.mark.asyncio
async def test_site_without_hatches_completes_exactly_as_before(client: AsyncClient, admin_headers):
    district_id = _new_district()
    site_id = _new_site(district_id)
    _, inspector_headers = await _user(client, admin_headers, "inspector", district_id)
    inspection_id = await _start(client, inspector_headers, site_id)

    hatches = await client.get(f"/api/v1/inspections/{inspection_id}/hatches", headers=inspector_headers)
    assert hatches.status_code == 200 and hatches.json() == []
    done = await client.patch(
        f"/api/v1/inspections/{inspection_id}", json={"status": "completed"}, headers=inspector_headers,
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "completed"
    assert done.json()["is_green"] is True


@pytest.mark.asyncio
async def test_legacy_checklist_inspection_with_hatch_defect_becomes_critical(client: AsyncClient, admin_headers):
    district_id = _new_district()
    site_id = _new_site(district_id)
    hatch_id = await _hatch(client, admin_headers, site_id, "1")
    _, inspector_headers = await _user(client, admin_headers, "inspector", district_id)
    inspection_id = await _start(client, inspector_headers, site_id)
    _exec("UPDATE inspections SET template_id=%(t)s WHERE id=%(i)s", {"t": LEGACY_TEMPLATE_ID, "i": inspection_id})

    issue_id = (await _put(client, inspector_headers, inspection_id, hatch_id, state="missing")).json()["issue_id"]
    await _photo(client, inspector_headers, issue_id)
    done = await client.patch(
        f"/api/v1/inspections/{inspection_id}", json={"status": "completed"}, headers=inspector_headers,
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "critical"


@pytest.mark.asyncio
async def test_reviewed_inspection_is_locked_for_owner(client: AsyncClient, admin_headers):
    district_id = _new_district()
    site_id = _new_site(district_id)
    hatch_id = await _hatch(client, admin_headers, site_id, "1")
    _, inspector_headers = await _user(client, admin_headers, "inspector", district_id)
    _, reviewer_headers = await _user(client, admin_headers, "reviewer", district_id)
    inspection_id = await _start(client, inspector_headers, site_id)
    await client.post(f"/api/v1/inspections/{inspection_id}/hatches/all-ok", headers=inspector_headers)
    assert (await client.patch(
        f"/api/v1/inspections/{inspection_id}", json={"status": "completed"}, headers=inspector_headers,
    )).status_code == 200
    assert (await client.patch(
        f"/api/v1/inspections/{inspection_id}", json={"status": "completed"}, headers=reviewer_headers,
    )).status_code == 200

    locked = await _put(client, inspector_headers, inspection_id, hatch_id, state="damaged")
    assert locked.status_code == 409


@pytest.mark.asyncio
async def test_other_district_reviewer_is_forbidden(client: AsyncClient, admin_headers):
    district_id, other_district_id = _new_district(), _new_district()
    site_id = _new_site(district_id)
    hatch_id = await _hatch(client, admin_headers, site_id, "1")
    _, inspector_headers = await _user(client, admin_headers, "inspector", district_id)
    _, stranger_headers = await _user(client, admin_headers, "reviewer", other_district_id)
    _, stranger_inspector = await _user(client, admin_headers, "inspector", other_district_id)
    inspection_id = await _start(client, inspector_headers, site_id)
    await _put(client, inspector_headers, inspection_id, hatch_id, state="damaged")

    assert (await client.get(f"/api/v1/sites/{site_id}/hatches", headers=stranger_headers)).status_code == 403
    assert (await client.get(f"/api/v1/sites/{site_id}/hatches", headers=stranger_inspector)).status_code == 403
    assert (await client.get(
        f"/api/v1/inspections/{inspection_id}/hatches", headers=stranger_headers,
    )).status_code == 403
    assert (await _put(client, stranger_headers, inspection_id, hatch_id, state="ok")).status_code == 403
    assert (await _put(client, stranger_inspector, inspection_id, hatch_id, state="ok")).status_code == 403
    assert (await client.post(
        f"/api/v1/inspections/{inspection_id}/hatches/all-ok", headers=stranger_headers,
    )).status_code == 403

    # Проверяющий закреплён за своим районом: чужой district_id в запросе
    # журнала игнорируется, а не открывает чужие данные.
    journal = await client.get(
        "/api/v1/hatches/journal", params={"district_id": district_id}, headers=stranger_headers,
    )
    assert journal.status_code == 200, journal.text
    assert journal.json()["total"] == 0 and journal.json()["kpis"]["defects_in_period"] == 0
    assert (await client.get("/api/v1/hatches/journal", headers=stranger_inspector)).status_code == 403


@pytest.mark.asyncio
async def test_reviewer_marked_defect_photo_can_be_added_by_inspection_owner(client: AsyncClient, admin_headers):
    district_id = _new_district()
    site_id = _new_site(district_id)
    hatch_id = await _hatch(client, admin_headers, site_id, "1")
    _, inspector_headers = await _user(client, admin_headers, "inspector", district_id)
    _, reviewer_headers = await _user(client, admin_headers, "reviewer", district_id)
    _, colleague_headers = await _user(client, admin_headers, "inspector", district_id)
    inspection_id = await _start(client, inspector_headers, site_id)

    by_reviewer = await _put(client, reviewer_headers, inspection_id, hatch_id, state="damaged")
    assert by_reviewer.status_code == 200, by_reviewer.text
    issue_id = by_reviewer.json()["issue_id"]
    await _photo(client, inspector_headers, issue_id)
    colleague = await client.post(
        f"/api/v1/issues/{issue_id}/photos",
        files={"file": ("x.jpg", b"\xff\xd8\xff", "image/jpeg")}, headers=colleague_headers,
    )
    assert colleague.status_code == 403


@pytest.mark.asyncio
async def test_site_hatches_show_last_check_today_and_open_issue(client: AsyncClient, admin_headers):
    district_id = _new_district()
    site_id = _new_site(district_id)
    first = await _hatch(client, admin_headers, site_id, "1", owner="МОЭК")
    second = await _hatch(client, admin_headers, site_id, "2")
    _, inspector_headers = await _user(client, admin_headers, "inspector", district_id)
    inspection_id = await _start(client, inspector_headers, site_id)
    issue_id = (await _put(client, inspector_headers, inspection_id, first, state="damaged")).json()["issue_id"]

    listed = await client.get(f"/api/v1/sites/{site_id}/hatches", headers=inspector_headers)
    assert listed.status_code == 200, listed.text
    by_number = {h["number"]: h for h in listed.json()}
    assert list(by_number) == ["1", "2"]
    assert by_number["1"]["checked_today"] is True
    assert by_number["1"]["last_check"]["state"] == "damaged"
    assert by_number["1"]["last_check"]["checked_by_name"] == "Люки inspector"
    assert by_number["1"]["open_issue"]["id"] == issue_id
    assert by_number["1"]["open_issue"]["status"] == "open"
    assert by_number["2"]["checked_today"] is False
    assert by_number["2"]["last_check"] is None and by_number["2"]["open_issue"] is None

    # Вчерашний осмотр — не «сегодня», но остаётся последним.
    _exec("UPDATE hatch_checks SET created_at = now() - interval '1 day' WHERE hatch_id=%(h)s", {"h": first})
    listed = (await client.get(f"/api/v1/sites/{site_id}/hatches", headers=admin_headers)).json()
    assert listed[0]["checked_today"] is False and listed[0]["last_check"]["state"] == "damaged"
    assert second  # второй люк без осмотров остаётся в списке


@pytest.mark.asyncio
async def test_journal_kpis_rows_and_filters(client: AsyncClient, admin_headers):
    district_id = _new_district()
    site_a = _new_site(district_id, "Улица А", section="Участок 1")
    site_b = _new_site(district_id, "Улица Б", section="Участок 2")
    a1 = await _hatch(client, admin_headers, site_a, "1", owner="Мосводоканал")
    a2 = await _hatch(client, admin_headers, site_a, "2")
    b1 = await _hatch(client, admin_headers, site_b, "1")
    await _hatch(client, admin_headers, site_b, "2")  # не осмотрен сегодня
    _, inspector_headers = await _user(client, admin_headers, "inspector", district_id)
    _, reviewer_headers = await _user(client, admin_headers, "reviewer", district_id)

    insp_a = await _start(client, inspector_headers, site_a)
    overdue_issue = (await _put(
        client, inspector_headers, insp_a, a1, state="damaged", fenced=True, owner_ticket="77",
    )).json()["issue_id"]
    await _photo(client, inspector_headers, overdue_issue)
    await _put(client, inspector_headers, insp_a, a2, state="ok")
    insp_b = await _start(client, inspector_headers, site_b)
    accepted_issue = (await _put(client, inspector_headers, insp_b, b1, state="missing")).json()["issue_id"]

    _exec("UPDATE issues SET due_date = current_date - 3 WHERE id=%(i)s", {"i": overdue_issue})
    admin_id = (await client.get("/api/v1/auth/me", headers=admin_headers)).json()["id"]
    _exec(
        "UPDATE issues SET status='closed' WHERE id=%(i)s;"
        "INSERT INTO issue_status_history(issue_id,old_status,new_status,changed_by) "
        "VALUES (%(i)s,'fixed','closed',%(u)s)",
        {"i": accepted_issue, "u": admin_id},
    )

    journal = await client.get("/api/v1/hatches/journal", params={"district_id": district_id}, headers=admin_headers)
    assert journal.status_code == 200, journal.text
    data = journal.json()
    assert data["kpis"] == {
        "checked_today": 3, "total_active_hatches": 4, "defects_in_period": 2,
        "not_fixed": 1, "overdue": 1,
    }
    assert data["total"] == 3 and [r["n"] for r in data["rows"]] == [1, 2, 3]
    assert data["sections"] == ["Участок 1", "Участок 2"]
    rows = {(r["site_id"], r["hatch_number"]): r for r in data["rows"]}
    damaged = rows[(site_a, "1")]
    assert damaged["state"] == "damaged" and damaged["has_photo"] is True
    assert damaged["hatch_owner"] == "Мосводоканал" and damaged["section"] == "Участок 1"
    assert damaged["measures"] == "ограждено; заявка № 77"
    assert damaged["fix_state"] == "overdue" and damaged["checked_by_name"] == "Люки inspector"
    assert rows[(site_a, "2")]["fix_state"] == "none" and rows[(site_a, "2")]["has_photo"] is False
    accepted = rows[(site_b, "1")]
    assert accepted["fix_state"] == "accepted" and accepted["closed_at"] is not None
    assert accepted["has_photo"] is False

    defects = (await client.get("/api/v1/hatches/journal", params={
        "district_id": district_id, "state": "defects",
    }, headers=admin_headers)).json()
    assert {r["state"] for r in defects["rows"]} == {"damaged", "missing"}
    by_state = (await client.get("/api/v1/hatches/journal", params={
        "district_id": district_id, "state": "ok",
    }, headers=admin_headers)).json()
    assert [r["hatch_id"] for r in by_state["rows"]] == [a2]
    section = (await client.get("/api/v1/hatches/journal", params={
        "district_id": district_id, "section": "Участок 2",
    }, headers=admin_headers)).json()
    assert [r["hatch_id"] for r in section["rows"]] == [b1]
    assert section["kpis"]["total_active_hatches"] == 2 and section["kpis"]["checked_today"] == 1
    paged = (await client.get("/api/v1/hatches/journal", params={
        "district_id": district_id, "page": 2, "page_size": 2,
    }, headers=admin_headers)).json()
    assert paged["total"] == 3 and [r["n"] for r in paged["rows"]] == [3]

    # Период: осмотр, перенесённый на прошлый месяц, выпадает из текущей
    # недели по умолчанию, но попадает в явно заданный период.
    _exec("UPDATE hatch_checks SET created_at = now() - interval '40 days' WHERE hatch_id=%(h)s", {"h": a2})
    week = (await client.get("/api/v1/hatches/journal", params={"district_id": district_id}, headers=admin_headers)).json()
    assert week["total"] == 2
    past = (datetime.now(MSK) - timedelta(days=40)).date()
    explicit = (await client.get("/api/v1/hatches/journal", params={
        "district_id": district_id, "date_from": str(past), "date_to": str(past),
    }, headers=admin_headers)).json()
    assert [r["hatch_id"] for r in explicit["rows"]] == [a2]

    pinned = (await client.get("/api/v1/hatches/journal", headers=reviewer_headers)).json()
    assert pinned["total"] == 2 and pinned["kpis"]["total_active_hatches"] == 4

    bad_state = await client.get("/api/v1/hatches/journal", params={"state": "broken"}, headers=admin_headers)
    assert bad_state.status_code == 422
    bad_period = await client.get("/api/v1/hatches/journal", params={
        "date_from": "2026-09-10", "date_to": "2026-09-01",
    }, headers=admin_headers)
    assert bad_period.status_code == 422


@pytest.mark.asyncio
async def test_journal_xlsx_has_paper_journal_columns(client: AsyncClient, admin_headers):
    district_id = _new_district()
    site_id = _new_site(district_id, "=HYPERLINK(\"x\")")
    hatch_id = await _hatch(client, admin_headers, site_id, "5", owner="Связь")
    _, inspector_headers = await _user(client, admin_headers, "inspector", district_id)
    inspection_id = await _start(client, inspector_headers, site_id)
    await _put(client, inspector_headers, inspection_id, hatch_id, state="sink", fenced=True, comment="=1+1")

    today = datetime.now(MSK).date()
    response = await client.get("/api/v1/hatches/journal.xlsx", params={
        "district_id": district_id, "date_from": str(today), "date_to": str(today),
    }, headers=admin_headers)
    assert response.status_code == 200, response.text
    assert f"zhurnal_lyukov_{today}_{today}.xlsx" in response.headers["content-disposition"]
    workbook = load_workbook(BytesIO(response.content))
    sheet = workbook["Журнал осмотра люков"]
    assert [cell.value for cell in sheet[1]] == JOURNAL_HEADERS
    assert sheet.freeze_panes == "A2"
    row = [cell.value for cell in sheet[2]]
    assert row[0] == 1
    assert row[5] == "№5 · Связь"
    assert row[6] == "Провал вокруг люка"
    assert row[7] == "нет"
    assert row[8] == "ограждено; =1+1"
    assert row[9] == "Люки inspector"
    assert row[10].startswith("В работе, срок ")
    # Пользовательский текст, похожий на формулу, остаётся текстом.
    assert all(cell.data_type != "f" for cell in sheet[2])
    assert sheet.max_row == 2
