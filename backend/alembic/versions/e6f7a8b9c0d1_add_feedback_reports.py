"""add feedback_reports

Revision ID: e6f7a8b9c0d1
Revises: d1e2f3a4b5c6
Create Date: 2026-08-11

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'e6f7a8b9c0d1'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Очередь обращений с публичной веб-формы (/feedback) — заявитель
    # может остаться анонимным, никакой связи с users. Отдельно от issues:
    # это жалобы граждан/сотрудников, а не находки инспектора при обходе.
    op.execute("DO $$ BEGIN "
               "CREATE TYPE feedback_status AS ENUM ('new', 'in_review', 'resolved', 'dismissed'); "
               "EXCEPTION WHEN duplicate_object THEN NULL; END $$;")
    op.execute(
        "CREATE TABLE IF NOT EXISTS feedback_reports ("
        "    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),"
        "    full_name      VARCHAR(200),"
        "    phone          VARCHAR(20),"
        "    location_text  VARCHAR(500),"
        "    message        TEXT NOT NULL,"
        "    status         feedback_status NOT NULL DEFAULT 'new',"
        "    admin_comment  TEXT,"
        "    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),"
        "    resolved_at    TIMESTAMPTZ"
        ")"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_feedback_reports_status ON feedback_reports(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_feedback_reports_created ON feedback_reports(created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS feedback_reports")
    op.execute("DROP TYPE IF EXISTS feedback_status")
