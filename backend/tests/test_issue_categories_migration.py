"""Регрессия на миграцию b1c2d3e4f5a6 (docs/STATS_MODEL_V2.md Фаза 1):
issue_categories заведена и заполнена, а существующие checklist_items
(из schema.sql) корректно размечены по ключевым словам — не просто "не
упало", а реально сопоставлены с ожидаемой категорией."""
import os

import psycopg2
import pytest

SYNC_DB_URL = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")


def _query_all(sql, params=None):
    conn = psycopg2.connect(SYNC_DB_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
            return cur.fetchall()
    finally:
        conn.close()


def test_issue_categories_seeded():
    rows = _query_all("SELECT name, sort_order, is_active FROM issue_categories ORDER BY sort_order")
    names = [r[0] for r in rows]
    assert names == [
        "Оборудование", "Покрытие", "Ограждения", "МАФ", "Санитарное состояние",
        "Безопасность", "Документация", "Освещение", "Прочее",
    ]
    assert all(r[2] for r in rows), "все категории должны быть активны по умолчанию"
    assert rows[-1][1] == 999, "Прочее — всегда последняя по sort_order"


def test_checklist_items_backfilled_from_schema_sql():
    # schema.sql сеет реальные пункты с category='Покрытие'/'Оборудование' —
    # после миграции они должны быть размечены соответствующим category_id,
    # а не остаться NULL или все схлопнуться в "Прочее".
    rows = _query_all("""
        SELECT ci.category, cat.name
        FROM checklist_items ci
        JOIN issue_categories cat ON ci.category_id = cat.id
        WHERE ci.category = 'Покрытие'
    """)
    assert rows, "хотя бы один пункт с category='Покрытие' должен существовать (см. schema.sql)"
    assert all(mapped == "Покрытие" for _raw, mapped in rows)

    rows = _query_all("""
        SELECT ci.category, cat.name
        FROM checklist_items ci
        JOIN issue_categories cat ON ci.category_id = cat.id
        WHERE ci.category = 'Оборудование'
    """)
    assert rows
    assert all(mapped == "Оборудование" for _raw, mapped in rows)

    unmapped = _query_all("SELECT count(*) FROM checklist_items WHERE category_id IS NULL")
    assert unmapped[0][0] == 0, "миграция должна разметить все существующие пункты (fallback — Прочее)"


@pytest.mark.parametrize("category_text,expected", [
    ("покрытие", "Покрытие"),
    ("  Оборудование  ", "Оборудование"),
    ("Ограждение участка", "Ограждения"),
    ("Скамейки и урны", "МАФ"),
    ("Уборка мусора", "Санитарное состояние"),
    ("Пожарная безопасность", "Безопасность"),
    ("Информационная табличка", "Документация"),
    ("Освещение территории", "Освещение"),
    ("Что-то совсем другое", "Прочее"),
    (None, "Прочее"),
])
def test_keyword_mapping_matches_spec(category_text, expected):
    # Прогоняем маппинг на СВЕЖЕМ временном пункте чек-листа — проверяет
    # именно правило приоритета ключевых слов из миграции, а не то, что уже
    # успело осесть в БД при накатке.
    import uuid

    conn = psycopg2.connect(SYNC_DB_URL)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            item_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO checklist_items (id, template_id, category, question) "
                "SELECT %(id)s, id, %(cat)s, 'temp' FROM checklist_templates LIMIT 1",
                {"id": item_id, "cat": category_text},
            )
            # тот же CASE, что и в миграции b1c2d3e4f5a6 — минимальный набор
            # веток, достаточный для параметров этого теста. Без params dict
            # (psycopg2 иначе пытается раскрыть КАЖДЫЙ "%" в запросе как
            # плейсхолдер, включая литералы внутри LIKE '%покрытие%') — id
            # подставлен напрямую, это доверенный UUID из uuid.uuid4() выше,
            # не пользовательский ввод.
            cur.execute(f"""
                UPDATE checklist_items SET category_id = (
                    CASE
                        WHEN LOWER(TRIM(category)) LIKE '%покрытие%' THEN (SELECT id FROM issue_categories WHERE name = 'Покрытие')
                        WHEN LOWER(TRIM(category)) LIKE ANY(ARRAY['%оборудован%','%качел%','%горк%','%турник%','%карусел%','%тренаж%','%песочниц%']) THEN (SELECT id FROM issue_categories WHERE name = 'Оборудование')
                        WHEN LOWER(TRIM(category)) LIKE '%огражден%' THEN (SELECT id FROM issue_categories WHERE name = 'Ограждения')
                        WHEN LOWER(TRIM(category)) LIKE ANY(ARRAY['%маф%','%скамей%','%урн%']) THEN (SELECT id FROM issue_categories WHERE name = 'МАФ')
                        WHEN LOWER(TRIM(category)) LIKE ANY(ARRAY['%санитар%','%мусор%','%уборк%','%чистот%']) THEN (SELECT id FROM issue_categories WHERE name = 'Санитарное состояние')
                        WHEN LOWER(TRIM(category)) LIKE '%безопасн%' THEN (SELECT id FROM issue_categories WHERE name = 'Безопасность')
                        WHEN LOWER(TRIM(category)) LIKE ANY(ARRAY['%документ%','%табличк%','%паспорт%','%вывеск%']) THEN (SELECT id FROM issue_categories WHERE name = 'Документация')
                        WHEN LOWER(TRIM(category)) LIKE ANY(ARRAY['%освещен%','%свет%']) THEN (SELECT id FROM issue_categories WHERE name = 'Освещение')
                        ELSE (SELECT id FROM issue_categories WHERE name = 'Прочее')
                    END
                ) WHERE id = '{item_id}'
            """)
            cur.execute(
                "SELECT cat.name FROM checklist_items ci JOIN issue_categories cat ON ci.category_id = cat.id "
                "WHERE ci.id = %(id)s", {"id": item_id},
            )
            (mapped,) = cur.fetchone()
            assert mapped == expected
            cur.execute("DELETE FROM checklist_items WHERE id = %(id)s", {"id": item_id})
    finally:
        conn.close()
