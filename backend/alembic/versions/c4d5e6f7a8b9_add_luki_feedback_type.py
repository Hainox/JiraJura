"""add 'luki' to feedback_report_type: обращения из приложения «Люки САО»

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-10-01
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # У «Люков САО» нет своей формы поддержки — «Написать в поддержку» ведёт
    # на /feedback?app=luki, и такие обращения должны отличаться от проблем
    # с журналом обходов в общем списке администратора.
    op.execute("ALTER TYPE feedback_report_type ADD VALUE IF NOT EXISTS 'luki'")


def downgrade() -> None:
    # Значение из enum в PostgreSQL не удалить — пересоздаём тип без него,
    # а уже пришедшие обращения про люки сохраняем как «Приложение».
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'feedback_report_type' AND e.enumlabel = 'luki'
          ) THEN
            UPDATE feedback_reports SET report_type = 'app' WHERE report_type::text = 'luki';
            ALTER TYPE feedback_report_type RENAME TO feedback_report_type_old;
            CREATE TYPE feedback_report_type AS ENUM ('site', 'app', 'other');
            ALTER TABLE feedback_reports ALTER COLUMN report_type DROP DEFAULT;
            ALTER TABLE feedback_reports ALTER COLUMN report_type
              TYPE feedback_report_type USING report_type::text::feedback_report_type;
            ALTER TABLE feedback_reports ALTER COLUMN report_type SET DEFAULT 'site';
            DROP TYPE feedback_report_type_old;
          END IF;
        END $$;
    """)
