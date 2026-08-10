"""add is_developer to users

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-08-10
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS — schema.sql (свежие инсталляции) уже содержит эту
    # колонку, upgrade head на такой БД проходит эту ревизию повторно
    # поверх уже применённого schema.sql.
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_developer "
        "BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS is_developer")
