"""add issue categories and executor name

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-08-20
"""
from typing import Sequence, Union

from alembic import op


revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEED_CATEGORIES = """
INSERT INTO issue_categories (name, sort_order) VALUES
    ('Оборудование', 10),
    ('Покрытие', 20),
    ('Ограждения', 30),
    ('МАФ', 40),
    ('Санитарное состояние', 50),
    ('Безопасность', 60),
    ('Документация', 70),
    ('Освещение', 80),
    ('Прочее', 999)
ON CONFLICT (name) DO UPDATE SET sort_order = EXCLUDED.sort_order
"""

# The order is intentional: sanitary wording wins for mixed descriptions such
# as "оборудование: уборка мусора".
CATEGORY_CASE = """
CASE
    WHEN lower(trim(%(exact)s)) = 'оборудование' THEN 'Оборудование'
    WHEN lower(trim(%(exact)s)) = 'покрытие' THEN 'Покрытие'
    WHEN lower(trim(%(exact)s)) IN ('ограждение', 'ограждения') THEN 'Ограждения'
    WHEN lower(trim(%(exact)s)) = 'маф' THEN 'МАФ'
    WHEN lower(trim(%(exact)s)) = 'санитарное состояние' THEN 'Санитарное состояние'
    WHEN lower(trim(%(exact)s)) = 'безопасность' THEN 'Безопасность'
    WHEN lower(trim(%(exact)s)) = 'документация' THEN 'Документация'
    WHEN lower(trim(%(exact)s)) = 'освещение' THEN 'Освещение'
    WHEN lower(trim(%(exact)s)) = 'прочее' THEN 'Прочее'
    WHEN lower(%(text)s) ~ '(санитар|мусор|уборк|чистот)' THEN 'Санитарное состояние'
    WHEN lower(%(text)s) LIKE '%%покрыти%%' THEN 'Покрытие'
    WHEN lower(%(text)s) ~ '(оборудован|качел|горк|турник|карусел|тренаж|песочниц)' THEN 'Оборудование'
    WHEN lower(%(text)s) LIKE '%%огражден%%' THEN 'Ограждения'
    WHEN lower(%(text)s) ~ '(маф|скамей|урн)' THEN 'МАФ'
    WHEN lower(%(text)s) LIKE '%%безопасн%%' THEN 'Безопасность'
    WHEN lower(%(text)s) ~ '(документ|табличк|паспорт|вывеск)' THEN 'Документация'
    WHEN lower(%(text)s) ~ '(освещен|свет)' THEN 'Освещение'
    ELSE 'Прочее'
END
"""


def _category_name(text_expression: str, *, exact_expression: str | None = None) -> str:
    return CATEGORY_CASE % {
        "text": text_expression,
        "exact": exact_expression or text_expression,
    }


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS issue_categories (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name VARCHAR(200) NOT NULL UNIQUE,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(SEED_CATEGORIES)
    op.execute("""
        ALTER TABLE checklist_items
        ADD COLUMN IF NOT EXISTS category_id UUID REFERENCES issue_categories(id)
    """)
    op.execute("""
        ALTER TABLE issues
        ADD COLUMN IF NOT EXISTS category_id UUID REFERENCES issue_categories(id)
    """)
    op.execute("ALTER TABLE issues ADD COLUMN IF NOT EXISTS executor_name VARCHAR(300)")

    checklist_category = _category_name(
        "concat_ws(' ', ci.category, ci.question)", exact_expression="ci.category"
    )
    op.execute(f"""
        UPDATE checklist_items AS ci
        SET category_id = categories.id
        FROM issue_categories AS categories
        WHERE ci.category_id IS NULL
          AND categories.name = {checklist_category}
    """)

    issue_category = _category_name("concat_ws(' ', i.title, i.description)")
    op.execute(f"""
        UPDATE issues AS i
        SET category_id = COALESCE(
            (
                SELECT ci.category_id
                FROM checklist_answers ca
                JOIN checklist_items ci ON ci.id = ca.checklist_item_id
                WHERE ca.id = i.checklist_answer_id
            ),
            (SELECT id FROM issue_categories WHERE name = {issue_category}),
            (SELECT id FROM issue_categories WHERE name = 'Прочее')
        )
        WHERE i.category_id IS NULL
    """)

    # Legacy overdue was a stored status. V2 derives it from due_date instead.
    op.execute("""
        UPDATE issues
        SET status = CASE WHEN assigned_to IS NULL THEN 'open'::issue_status
                          ELSE 'assigned'::issue_status END
        WHERE status = 'overdue'::issue_status
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_checklist_items_category_id ON checklist_items(category_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_issues_category_id ON issues(category_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_issues_category_id")
    op.execute("DROP INDEX IF EXISTS idx_checklist_items_category_id")
    op.execute("ALTER TABLE issues DROP COLUMN IF EXISTS executor_name")
    op.execute("ALTER TABLE issues DROP COLUMN IF EXISTS category_id")
    op.execute("ALTER TABLE checklist_items DROP COLUMN IF EXISTS category_id")
    op.execute("DROP TABLE IF EXISTS issue_categories")
