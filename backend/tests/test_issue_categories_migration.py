"""Contract checks for the expand migration of statistics v2."""

import pytest
from sqlalchemy import text


EXPECTED_CATEGORIES = [
    ("Оборудование", 10),
    ("Покрытие", 20),
    ("Ограждения", 30),
    ("МАФ", 40),
    ("Санитарное состояние", 50),
    ("Безопасность", 60),
    ("Документация", 70),
    ("Освещение", 80),
    ("Прочее", 999),
]


@pytest.mark.asyncio
async def test_issue_category_seed_and_backfill_are_complete():
    from app.database import async_session, engine

    try:
        async with async_session() as db:
            categories = (
                await db.execute(
                    text("SELECT name, sort_order FROM issue_categories ORDER BY sort_order")
                )
            ).all()
            missing_items = await db.scalar(
                text("SELECT count(*) FROM checklist_items WHERE category_id IS NULL")
            )
            overdue_issues = await db.scalar(
                text("SELECT count(*) FROM issues WHERE status = 'overdue'::issue_status")
            )
            nullable_columns = (
                await db.execute(text("""
                    SELECT table_name, column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND (table_name, column_name) IN (
                        ('checklist_items', 'category_id'), ('issues', 'category_id')
                      )
                      AND is_nullable = 'YES'
                """))
            ).all()
    finally:
        # pytest-asyncio uses a separate loop per test; never leave pooled
        # asyncpg connections attached to the loop that is about to close.
        await engine.dispose()

    assert categories == EXPECTED_CATEGORIES
    assert missing_items == 0
    assert overdue_issues == 0
    assert nullable_columns == []


def test_models_expose_expand_columns():
    from app.models import ChecklistItem, Issue, IssueCategory

    assert IssueCategory.__table__.c.name.unique
    assert not ChecklistItem.__table__.c.category_id.nullable
    assert not Issue.__table__.c.category_id.nullable
    assert Issue.__table__.c.executor_name.type.length == 300
