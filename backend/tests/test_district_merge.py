"""Регрессия: merge_district раньше 500'ил и откатывал весь merge, если на
исходный район ещё ссылался пользователь или неиспользованное приглашение
(оба FK — без ON DELETE). Ровно так продовый "Бескудниковский;Восточное
Дегунино" не смёрживался с первой попытки."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_merge_reassigns_users_and_invites_and_succeeds(client: AsyncClient, admin_headers):
    r = await client.get("/api/v1/districts/", headers=admin_headers)
    districts = r.json()
    src_id = districts[0]["id"]
    dst_id = districts[1]["id"]

    # пользователь и неиспользованное приглашение, оба всё ещё числятся за
    # исходным районом — именно это раньше валило DELETE FROM districts
    invite = await client.post("/api/v1/auth/invites", json={
        "login": "MergeTestUser", "full_name": "Тестов Мерджтестович",
        "role": "inspector", "district_id": src_id,
    }, headers=admin_headers)
    assert invite.status_code == 200, invite.text

    r = await client.post(f"/api/v1/districts/{src_id}/merge", json={"into_district_id": dst_id}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == dst_id

    r = await client.get("/api/v1/districts/admin", headers=admin_headers)
    remaining_ids = {d["id"] for d in r.json()}
    assert src_id not in remaining_ids

    r = await client.get("/api/v1/auth/invites/pending", headers=admin_headers)
    reassigned = next(i for i in r.json() if i["login"] == "MergeTestUser")
    assert reassigned["district_id"] == dst_id
