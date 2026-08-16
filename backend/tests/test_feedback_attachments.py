import pytest


@pytest.mark.asyncio
async def test_feedback_accepts_more_than_five_attachments(client, tmp_path, monkeypatch):
    """Количество вложений у обращения не ограничено прикладным лимитом."""
    from app.routers import feedback

    monkeypatch.setattr(feedback, "UPLOAD_DIR", str(tmp_path))

    created = await client.post(
        "/api/v1/feedback/",
        json={"report_type": "app", "message": "Проверка множественных вложений"},
    )
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]

    for index in range(6):
        uploaded = await client.post(
            f"/api/v1/feedback/{report_id}/attachments",
            files={"file": (f"screenshot-{index}.png", b"test-image", "image/png")},
        )
        assert uploaded.status_code == 201, uploaded.text

    feedback_dir = tmp_path / "feedback"
    assert len(list(feedback_dir.iterdir())) == 6
