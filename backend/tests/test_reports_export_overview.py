"""Регрессия: /reports/export.xlsx раньше не содержал листов "Обзор" и
"Регистрация" из эталонного generate_summary_report.py — тот скрипт
годами запускался только вручную на сервере, хотя пользователь просил
привести именно кнопку "Excel" в приложении к этому формату."""
import io

import pytest
from httpx import AsyncClient
from openpyxl import load_workbook


@pytest.mark.asyncio
async def test_export_includes_overview_and_registration_sheets(client: AsyncClient, admin_headers):
    r = await client.get("/api/v1/reports/export.xlsx", headers=admin_headers)
    assert r.status_code == 200, r.text

    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames[0] == "Обзор"
    assert "Регистрация" in wb.sheetnames

    ov = wb["Обзор"]
    ov_text = "\n".join(str(c.value) for row in ov.iter_rows() for c in row if c.value is not None)
    assert "Ключевые цифры" in ov_text
    assert "Регистрация" in ov_text
    assert "Состав отчёта" in ov_text

    reg = wb["Регистрация"]
    headers = [c.value for c in reg[4]]
    assert headers == ["Район", "Зарегистрировано", "Всего приглашено", "% регистрации"]
    reg_text = "\n".join(str(c.value) for row in reg.iter_rows() for c in row if c.value is not None)
    assert "ИТОГО" in reg_text


@pytest.mark.asyncio
async def test_reviewer_registration_sheet_scoped_to_own_district(client: AsyncClient, admin_headers):
    r = await client.get("/api/v1/districts/", headers=admin_headers)
    districts = r.json()
    district_id, other_district_id = districts[0]["id"], districts[1]["id"]

    invite = await client.post("/api/v1/auth/invites", json={
        "login": "OverviewTestReviewer", "full_name": "Обзоров Тест Тестович",
        "role": "reviewer", "district_id": district_id,
    }, headers=admin_headers)
    token = invite.json()["token"]
    complete = await client.post(f"/api/v1/auth/invites/{token}/complete", json={"password": "Test12345"})
    reviewer_headers = {"Authorization": f"Bearer {complete.json()['access_token']}"}

    r = await client.get("/api/v1/reports/export.xlsx", headers=reviewer_headers)
    assert r.status_code == 200, r.text

    wb = load_workbook(io.BytesIO(r.content))
    reg = wb["Регистрация"]
    # ровно свой район в разбивке (плюс строка ИТОГО), не весь список
    # районов округа
    named_rows = [
        row for row in reg.iter_rows(min_row=5, values_only=True)
        if row[0] and row[0] != "ИТОГО" and isinstance(row[1], int)
    ]
    assert len(named_rows) == 1
    assert named_rows[0][0] != districts[1]["name"]
