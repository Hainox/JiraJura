"""add issue_categories

Revision ID: b1c2d3e4f5a6
Revises: a8b9c0d1e2f3
Create Date: 2026-08-19

Фаза 1 из docs/STATS_MODEL_V2.md: справочник категорий нарушений +
category_id на checklist_items/issues + executor_name на issues, с
разовым пересчётом category_id по существующим данным. Ничего не
ломает — только nullable-добавления и новая независимая таблица;
старая колонка checklist_items.category остаётся (deprecated, код её
больше не читает), т.к. на неё нет внешних ссылок и удалять её
отдельная, необязательная для этой фазы задача.
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = 'a8b9c0d1e2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Ключевые слова в порядке приоритета — первое совпадение побеждает (пункт
# вида "фото при уборке мусора" должен уйти в Санитарное, а не потеряться
# в более общей категории, если бы порядок был другим).
_CATEGORY_KEYWORDS = [
    ("Покрытие", ["покрытие"]),
    ("Оборудование", ["оборудован", "качел", "горк", "турник", "карусел", "тренаж", "песочниц"]),
    ("Ограждения", ["огражден"]),
    ("МАФ", ["маф", "скамей", "урн"]),
    ("Санитарное состояние", ["санитар", "мусор", "уборк", "чистот"]),
    ("Безопасность", ["безопасн"]),
    ("Документация", ["документ", "табличк", "паспорт", "вывеск"]),
    ("Освещение", ["освещен", "свет"]),
]


def _keyword_case_sql(column_expr: str) -> str:
    """CASE WHEN <column_expr> LIKE ANY(...) ... ELSE 'Прочее' END — общий
    для checklist_items.category (нормализованный текст) и issues.title
    (сырой текст замечания), поэтому вынесено в одну функцию."""
    branches = []
    for name, keywords in _CATEGORY_KEYWORDS:
        patterns = ", ".join(f"'%{kw}%'" for kw in keywords)
        branches.append(
            f"        WHEN {column_expr} LIKE ANY(ARRAY[{patterns}]) "
            f"THEN (SELECT id FROM issue_categories WHERE name = '{name}')"
        )
    branches_sql = "\n".join(branches)
    return (
        "CASE\n" + branches_sql + "\n"
        "        ELSE (SELECT id FROM issue_categories WHERE name = 'Прочее')\n"
        "    END"
    )


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS issue_categories ("
        "    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),"
        "    name        VARCHAR(200) NOT NULL UNIQUE,"
        "    sort_order  INTEGER NOT NULL DEFAULT 0,"
        "    is_active   BOOLEAN NOT NULL DEFAULT true,"
        "    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    )

    op.execute(
        "INSERT INTO issue_categories (name, sort_order) VALUES "
        "('Оборудование', 10), ('Покрытие', 20), ('Ограждения', 30), "
        "('МАФ', 40), ('Санитарное состояние', 50), ('Безопасность', 60), "
        "('Документация', 70), ('Освещение', 80), ('Прочее', 999) "
        "ON CONFLICT (name) DO NOTHING"
    )

    op.execute(
        "ALTER TABLE checklist_items ADD COLUMN IF NOT EXISTS category_id UUID "
        "REFERENCES issue_categories(id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_checklist_items_category "
        "ON checklist_items(category_id)"
    )
    op.execute(
        "ALTER TABLE issues ADD COLUMN IF NOT EXISTS category_id UUID "
        "REFERENCES issue_categories(id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_issues_category ON issues(category_id)"
    )
    op.execute(
        "ALTER TABLE issues ADD COLUMN IF NOT EXISTS executor_name VARCHAR(300)"
    )

    # ── Пересчёт category_id по существующим данным ──
    checklist_case = _keyword_case_sql("LOWER(TRIM(ci.category))")
    op.execute(
        f"UPDATE checklist_items ci SET category_id = {checklist_case} "
        f"WHERE ci.category_id IS NULL"
    )

    issue_title_case = _keyword_case_sql("LOWER(i.title)")
    op.execute(
        "UPDATE issues i SET category_id = COALESCE("
        "    (SELECT ci.category_id FROM checklist_answers ca "
        "     JOIN checklist_items ci ON ca.checklist_item_id = ci.id "
        "     WHERE ca.id = i.checklist_answer_id),"
        f"    {issue_title_case}"
        ") "
        "WHERE i.category_id IS NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE issues DROP COLUMN IF EXISTS executor_name")
    op.execute("ALTER TABLE issues DROP COLUMN IF EXISTS category_id")
    op.execute("ALTER TABLE checklist_items DROP COLUMN IF EXISTS category_id")
    op.execute("DROP TABLE IF EXISTS issue_categories")
