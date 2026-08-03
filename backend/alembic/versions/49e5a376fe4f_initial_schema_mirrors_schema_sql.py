"""initial schema (mirrors schema.sql)

Пишется вручную, а не через --autogenerate: PostGIS-специфичные конструкции
(GENERATED ALWAYS AS (ST_Centroid(geometry)) STORED, GIST-индексы) и уже
существующие в БД именованные ENUM-типы (create_type=False в models.py)
автогенерация распознаёт неверно (см. docs — сравнение зафиксировано вручную).
Вместо транскрибирования DDL в op.*-вызовы построчно, выполняем содержимое
schema.sql как есть — это гарантирует, что миграция и файл быстрого
локального бутстрапа (docker-entrypoint-initdb.d/schema.sql) никогда не
разойдутся: schema.sql остаётся единственным источником правды.

Revision ID: 49e5a376fe4f
Revises:
Create Date: 2026-08-03 07:41:35.460904

"""
import re
from pathlib import Path
from typing import Sequence, Union

import sqlparse
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '49e5a376fe4f'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA_SQL_PATH = Path(__file__).resolve().parents[2] / "schema.sql"


def _statements(sql_text: str) -> list[str]:
    """Разбить .sql-файл на отдельные операторы.

    asyncpg исполняет через prepared statements и не может выполнить
    несколько команд одной строкой ("cannot insert multiple commands into
    a prepared statement"), поэтому schema.sql нужно выполнять оператор за
    оператором. Наивный split по ';' ломается на возможных ';' внутри
    строковых литералов — используем sqlparse, который это учитывает.
    """
    out = []
    for stmt in sqlparse.split(sql_text):
        stmt = stmt.strip()
        if not stmt:
            continue
        if not re.sub(r"--.*", "", stmt).strip():
            continue  # блок из одних комментариев — нечего выполнять
        out.append(stmt)
    return out


def upgrade() -> None:
    sql = SCHEMA_SQL_PATH.read_text(encoding="utf-8")
    for statement in _statements(sql):
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_invites CASCADE")
    op.execute("DROP TABLE IF EXISTS issue_status_history CASCADE")
    op.execute("DROP TABLE IF EXISTS issues CASCADE")
    op.execute("DROP TABLE IF EXISTS photos CASCADE")
    op.execute("DROP TABLE IF EXISTS checklist_answers CASCADE")
    op.execute("DROP TABLE IF EXISTS checklist_items CASCADE")
    op.execute("DROP TABLE IF EXISTS checklist_templates CASCADE")
    op.execute("DROP TABLE IF EXISTS inspections CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
    op.execute("DROP TABLE IF EXISTS equipment CASCADE")
    op.execute("DROP TABLE IF EXISTS sites CASCADE")
    op.execute("DROP TABLE IF EXISTS courtyards CASCADE")
    op.execute("DROP TABLE IF EXISTS districts CASCADE")
    op.execute("DROP TYPE IF EXISTS issue_status")
    op.execute("DROP TYPE IF EXISTS issue_criticality")
    op.execute("DROP TYPE IF EXISTS photo_target")
    op.execute("DROP TYPE IF EXISTS checklist_result")
    op.execute("DROP TYPE IF EXISTS inspection_status")
    op.execute("DROP TYPE IF EXISTS inspection_type")
    op.execute("DROP TYPE IF EXISTS user_role")
    op.execute("DROP TYPE IF EXISTS equipment_type")
    op.execute("DROP TYPE IF EXISTS site_type")
