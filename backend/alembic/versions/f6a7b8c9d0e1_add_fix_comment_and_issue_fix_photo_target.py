"""add fix_comment to issues + issue_fix photo_target value

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-05

`Issue.fix_comment` existed in the SQLAlchemy model (used by
`POST /issues/{id}/fix-photos` flow and `IssueUpdate.fix_comment`) but was
never added to `schema.sql` or any prior migration — any query touching the
`issues` table (create/list/get/update) fails with
`UndefinedColumnError: column issues.fix_comment does not exist`.

`photo_target` enum also never gained an `'issue_fix'` value, even though
`upload_fix_photo` inserts photos with `target_type='issue_fix'` — that
insert fails with `invalid input value for enum photo_target`.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS — schema.sql (свежие инсталляции) теперь тоже содержит
    # эту колонку и значение enum, upgrade head на такой БД проходит эту
    # ревизию повторно поверх уже применённого schema.sql.
    op.execute("ALTER TABLE issues ADD COLUMN IF NOT EXISTS fix_comment TEXT")
    # ALTER TYPE ... ADD VALUE нельзя выполнить внутри транзакции
    op.execute("COMMIT")
    op.execute("ALTER TYPE photo_target ADD VALUE IF NOT EXISTS 'issue_fix'")


def downgrade() -> None:
    op.drop_column('issues', 'fix_comment')
    # Удалить значение из enum нельзя в PostgreSQL — оставляем как есть
