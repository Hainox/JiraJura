"""add reviewer fields to inspections

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-04

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE inspections ADD COLUMN IF NOT EXISTS reviewer_comment TEXT")
    op.execute("ALTER TABLE inspections ADD COLUMN IF NOT EXISTS reviewed_by UUID REFERENCES users(id)")
    op.execute("ALTER TABLE inspections ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE inspections DROP COLUMN IF EXISTS reviewed_at")
    op.execute("ALTER TABLE inspections DROP COLUMN IF EXISTS reviewed_by")
    op.execute("ALTER TABLE inspections DROP COLUMN IF EXISTS reviewer_comment")
