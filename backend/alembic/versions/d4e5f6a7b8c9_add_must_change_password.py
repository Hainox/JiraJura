"""add must_change_password to users

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-04
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS — schema.sql (свежие инсталляции) теперь тоже содержит
    # эту колонку, upgrade head на такой БД проходит эту ревизию повторно
    # поверх уже применённого schema.sql.
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password "
        "BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.drop_column('users', 'must_change_password')
