"""add section to courtyards

Revision ID: e1f2a3b4c5d6
Revises: d2e3f4a5b6c7
Create Date: 2026-09-04
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'd2e3f4a5b6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS — schema.sql (свежие инсталляции) уже содержит эту
    # колонку, upgrade head на такой БД проходит эту ревизию повторно
    # поверх уже применённого schema.sql.
    op.execute(
        "ALTER TABLE courtyards ADD COLUMN IF NOT EXISTS section "
        "VARCHAR(50)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE courtyards DROP COLUMN IF EXISTS section")
