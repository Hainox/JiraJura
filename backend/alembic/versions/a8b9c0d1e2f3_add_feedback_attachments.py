"""add feedback_attachments

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-08-11

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'a8b9c0d1e2f3'
down_revision: Union[str, None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Фото или файлы (списки и т.п.), приложенные к обращению — не Photo,
    # та привязана к обходу/замечанию/оборудованию и подразумевает именно фото.
    op.execute(
        "CREATE TABLE IF NOT EXISTS feedback_attachments ("
        "    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),"
        "    feedback_report_id  UUID NOT NULL REFERENCES feedback_reports(id) ON DELETE CASCADE,"
        "    storage_path        VARCHAR(500) NOT NULL,"
        "    original_filename   VARCHAR(255),"
        "    content_type        VARCHAR(100),"
        "    size_bytes          INT,"
        "    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_feedback_attachments_report "
        "ON feedback_attachments(feedback_report_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS feedback_attachments")
