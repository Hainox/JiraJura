"""add audit_log table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-04
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = 'c3d4e5f6a7b8'
down_revision: str | None = 'b2c3d4e5f6a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # IF NOT EXISTS — schema.sql (свежие инсталляции) теперь тоже создаёт
    # эту таблицу, upgrade head на такой БД проходит эту ревизию повторно
    # поверх уже применённого schema.sql.
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
            action      VARCHAR(50) NOT NULL,
            entity_type VARCHAR(50) NOT NULL,
            entity_id   VARCHAR(100),
            details     TEXT,
            created_at  TIMESTAMPTZ DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.drop_table('audit_log')
