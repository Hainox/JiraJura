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
    # Добавляем 'revision_needed' в enum
    op.execute("ALTER TYPE issue_status ADD VALUE 'revision_needed'")
    # Добавляем reviewer_comment в таблицу issues
    op.add_column('issues', sa.Column('reviewer_comment', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('issues', 'reviewer_comment')
    # Удалить значение из enum в PostgreSQL нельзя — оставляем
