"""add is_active to checklist_items

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-10
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS — schema.sql (свежие инсталляции) уже содержит эту
    # колонку, upgrade head на такой БД проходит эту ревизию повторно
    # поверх уже применённого schema.sql.
    op.execute(
        "ALTER TABLE checklist_items ADD COLUMN IF NOT EXISTS is_active "
        "BOOLEAN NOT NULL DEFAULT true"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE checklist_items DROP COLUMN IF EXISTS is_active")
