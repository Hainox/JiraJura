"""add checklist_answer_id to photos

Revision ID: a1b2c3d4e5f6
Revises: 49e5a376fe4f
Create Date: 2026-08-04

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '49e5a376fe4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE нельзя выполнить внутри транзакции
    op.execute("COMMIT")
    op.execute("ALTER TYPE photo_target ADD VALUE IF NOT EXISTS 'checklist_answer'")
    op.execute("ALTER TABLE photos ADD COLUMN IF NOT EXISTS checklist_answer_id UUID REFERENCES checklist_answers(id) ON DELETE SET NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE photos DROP COLUMN IF EXISTS checklist_answer_id")
    # Удалить значение из enum нельзя в PostgreSQL — оставляем как есть
