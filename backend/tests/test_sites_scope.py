"""Регрессии для жалоб «площадки исчезли» после смены района/назначения."""
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text


async def _create_site(district_id: str, suffix: str) -> str:
    from app.database import async_session

    async with async_session() as db:
        courtyard_id = (
            await db.execute(
                text(
                    "INSERT INTO courtyards (district_id, name) "
                    "VALUES (CAST(:district_id AS uuid), :name) RETURNING id"
                ),
                {"district_id": district_id, "name": f"Тестовый двор {suffix}"},
            )
        ).scalar_one()
        site_id = (
            await db.execute(
                text(
                    "INSERT INTO sites "
                    "(courtyard_id, type, area_m2, geometry, is_active) "
                    "VALUES (CAST(:courtyard_id AS uuid), 'Детская площадка', 100, "
                    "ST_GeomFromText('POLYGON((37.50 55.80,37.51 55.80,"
                    "37.51 55.81,37.50 55.81,37.50 55.80))', 4326), TRUE) "
                    "RETURNING id"
                ),
                {"courtyard_id": courtyard_id},
            )
        ).scalar_one()
        await db.commit()
        return str(site_id)


async def _create_inspector(
    client: AsyncClient,
    admin_headers: dict[str, str],
    district_id: str,
    login: str,
) -> tuple[str, dict[str, str]]:
    invite = await client.post(
        "/api/v1/auth/invites",
        json={
            "login": login,
            "full_name": "Тестовый Инспектор",
            "role": "inspector",
            "district_id": district_id,
        },
        headers=admin_headers,
    )
    assert invite.status_code == 200, invite.text

    complete = await client.post(
        f"/api/v1/auth/invites/{invite.json()['token']}/complete",
        json={"password": "ScopeTest123"},
    )
    assert complete.status_code == 200, complete.text
    payload = complete.json()
    return payload["user"]["id"], {
        "Authorization": f"Bearer {payload['access_token']}"
    }


@pytest.mark.asyncio
async def test_stale_district_query_does_not_hide_sites_after_user_move(
    client: AsyncClient,
    admin_headers,
):
    districts = (await client.get("/api/v1/districts/", headers=admin_headers)).json()
    old_district_id = districts[0]["id"]
    new_district_id = districts[1]["id"]
    old_site_id = await _create_site(old_district_id, f"old-{uuid4()}")
    new_site_id = await _create_site(new_district_id, f"new-{uuid4()}")

    user_id, inspector_headers = await _create_inspector(
        client,
        admin_headers,
        old_district_id,
        f"scope_move_{uuid4().hex[:8]}",
    )
    assigned = await client.patch(
        f"/api/v1/sites/{old_site_id}/assign",
        json={"inspector_id": user_id},
        headers=admin_headers,
    )
    assert assigned.status_code == 200, assigned.text

    moved = await client.patch(
        f"/api/v1/auth/users/{user_id}",
        json={"district_id": new_district_id},
        headers=admin_headers,
    )
    assert moved.status_code == 200, moved.text

    # Имитируем уже открытую вкладку: токен остаётся прежним, а cached URL
    # всё ещё содержит старый district_id. Сервер должен доверять свежему
    # району пользователя из БД и вернуть площадки нового района.
    response = await client.get(
        "/api/v1/sites/",
        params={"district_id": old_district_id, "page_size": 5000},
        headers=inspector_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["total"] >= 1
    assert new_site_id in {item["id"] for item in response.json()["items"]}
    assert {item["district"]["id"] for item in response.json()["items"]} == {
        new_district_id
    }

    # Старое персональное назначение очищается при переносе, чтобы админка
    # не показывала недоступную сотруднику площадку как назначенную ему.
    old_site = await client.get(
        f"/api/v1/sites/{old_site_id}", headers=admin_headers
    )
    assert old_site.status_code == 200, old_site.text
    assert old_site.json()["assigned_inspector"] is None


@pytest.mark.asyncio
async def test_cannot_assign_site_to_inspector_from_another_district(
    client: AsyncClient,
    admin_headers,
):
    districts = (await client.get("/api/v1/districts/", headers=admin_headers)).json()
    site_district_id = districts[2]["id"]
    inspector_district_id = districts[3]["id"]
    site_id = await _create_site(site_district_id, f"cross-{uuid4()}")
    user_id, _ = await _create_inspector(
        client,
        admin_headers,
        inspector_district_id,
        f"scope_cross_{uuid4().hex[:8]}",
    )

    response = await client.patch(
        f"/api/v1/sites/{site_id}/assign",
        json={"inspector_id": user_id},
        headers=admin_headers,
    )
    assert response.status_code == 400, response.text
    assert "одному району" in response.json()["detail"]
