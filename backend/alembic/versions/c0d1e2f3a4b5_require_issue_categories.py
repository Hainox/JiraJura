"""require category foreign keys after v2 writer migration

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-08-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c0d1e2f3a4b5"
down_revision: Union[str, None] = "b9c0d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE checklist_items
        SET category_id = (SELECT id FROM issue_categories WHERE name = 'Прочее')
        WHERE category_id IS NULL
    """)
    op.execute("""
        UPDATE issues
        SET category_id = (SELECT id FROM issue_categories WHERE name = 'Прочее')
        WHERE category_id IS NULL
    """)
    op.execute("ALTER TABLE checklist_items ALTER COLUMN category_id SET NOT NULL")
    op.execute("ALTER TABLE issues ALTER COLUMN category_id SET NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE issues ALTER COLUMN category_id DROP NOT NULL")
    op.execute("ALTER TABLE checklist_items ALTER COLUMN category_id DROP NOT NULL")
