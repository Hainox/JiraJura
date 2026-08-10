"""add revision_needed to issue_status + reviewer_comment to issues

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-05
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS — schema.sql (свежие инсталляции) теперь тоже содержит
    # это значение enum и колонку, upgrade head на такой БД проходит эту
    # ревизию повторно поверх уже применённого schema.sql.
    # ALTER TYPE ... ADD VALUE нельзя выполнить внутри транзакции.
    op.execute("COMMIT")
    op.execute("ALTER TYPE issue_status ADD VALUE IF NOT EXISTS 'revision_needed'")
    op.execute("ALTER TABLE issues ADD COLUMN IF NOT EXISTS reviewer_comment TEXT")


def downgrade() -> None:
    op.drop_column('issues', 'reviewer_comment')
    # Удалить значение из enum в PostgreSQL нельзя — оставляем
