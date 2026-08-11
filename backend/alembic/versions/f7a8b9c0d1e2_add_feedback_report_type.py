"""add report_type to feedback_reports

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-08-11

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, None] = 'e6f7a8b9c0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # site — жалоба по площадке/двору; app — техническая проблема с самим
    # приложением (не заходит, баг, что-то не отображается); other — всё
    # остальное. Определяет, какие поля показывает форма на фронтенде.
    op.execute("DO $$ BEGIN "
               "CREATE TYPE feedback_report_type AS ENUM ('site', 'app', 'other'); "
               "EXCEPTION WHEN duplicate_object THEN NULL; END $$;")
    op.execute(
        "ALTER TABLE feedback_reports ADD COLUMN IF NOT EXISTS report_type "
        "feedback_report_type NOT NULL DEFAULT 'site'"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_feedback_reports_type ON feedback_reports(report_type)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_feedback_reports_type")
    op.execute("ALTER TABLE feedback_reports DROP COLUMN IF EXISTS report_type")
    op.execute("DROP TYPE IF EXISTS feedback_report_type")
