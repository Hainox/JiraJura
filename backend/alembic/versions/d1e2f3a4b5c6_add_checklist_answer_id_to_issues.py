"""add checklist_answer_id to issues

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
Create Date: 2026-08-11

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Связывает автоматически созданное замечание с конкретным пунктом
    # чек-листа, из-за которого оно появилось (см. update_inspection) —
    # уникальность на пункт не даёт задвоить замечание при повторном
    # сохранении того же обхода. NULL — для замечаний, созданных вручную
    # не по пункту чек-листа.
    op.execute(
        "ALTER TABLE issues ADD COLUMN IF NOT EXISTS checklist_answer_id UUID "
        "REFERENCES checklist_answers(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_issues_checklist_answer_id "
        "ON issues(checklist_answer_id) WHERE checklist_answer_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_issues_checklist_answer_id")
    op.execute("ALTER TABLE issues DROP COLUMN IF EXISTS checklist_answer_id")
