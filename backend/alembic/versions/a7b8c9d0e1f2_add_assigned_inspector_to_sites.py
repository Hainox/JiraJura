"""add assigned_inspector_id to sites

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-08
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS — schema.sql (свежие инсталляции) уже содержит эту
    # колонку, upgrade head на такой БД проходит эту ревизию повторно поверх
    # уже применённого schema.sql (см. соседние ревизии a1b2c3d4e5f6/b2c3d4e5f6a7).
    op.execute(
        "ALTER TABLE sites ADD COLUMN IF NOT EXISTS assigned_inspector_id "
        "UUID REFERENCES users(id) ON DELETE SET NULL"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_sites_assigned_inspector ON sites(assigned_inspector_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_sites_assigned_inspector")
    op.execute("ALTER TABLE sites DROP COLUMN IF EXISTS assigned_inspector_id")
