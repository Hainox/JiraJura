# -*- coding: utf-8 -*-
"""Разметка Courtyard.section (участок внутри района) по публичной карте
karta-sao (https://hainox.github.io/karta-sao/, areas.geojson) — источник
для внутрирайонного свода по участкам (см. StatisticsService.sections),
который районы попросили для углублённого контроля своих мест. На
окружной штаб этот разрез не подаётся, формат общего доклада не меняется.

areas.geojson — не крупные регионы, а полигон КАЖДОГО двора отдельно,
с district/section в properties. Матчинг здесь пространственный (по
координатам), а не по названию: для каждой активной площадки берём
центроид её геометрии и ищем полигон karta-sao того же района, в который
этот центроид попадает. У двора может быть несколько площадок — участок
двора определяется большинством голосов его площадок; при равенстве
голосов или отсутствии совпадений двор попадает в отчёт на ручной разбор
и НЕ изменяется.

Названия районов в основном совпадают дословно с schema.sql, кроме
одного: "Савеловский" в karta-sao против "Савёловский" в JiraJura (ё/е) —
см. DISTRICT_NAME_ALIASES.

По умолчанию — только отчёт (dry-run), без изменений в БД. Применение —
флаг --apply. Дворы, у которых section уже проставлен (например, вручную
поправлен через админку), по умолчанию не трогаются — это защита от
переписывания ручной правки; чтобы всё же пересчитать такие дворы тоже
(например, после обновления geojson), используйте --force. UPDATE идёт
с условием "section в БД не изменился с момента SELECT" — та же защита от
гонки с параллельной правкой через API, что и в других backfill-скриптах
проекта (см. backfill_maf_due_dates.py).

Файл geojson не скачивается самим скриптом (сеть на сервере не нужна для
этого шага) — передайте локальный путь через --geojson.

Примеры:
  dry-run: python assign_courtyard_sections.py \
             --db-url postgresql://postgres:postgres@db:5432/sao_inspection \
             --geojson areas.geojson
  апплай:  python assign_courtyard_sections.py \
             --db-url postgresql://postgres:postgres@db:5432/sao_inspection \
             --geojson areas.geojson --apply
"""
import argparse
import json
from collections import Counter, defaultdict

import psycopg2
from psycopg2.extras import execute_values

DISTRICT_NAME_ALIASES = {
    "Савеловский": "Савёловский",
}


def load_areas(geojson_path):
    with open(geojson_path, encoding="utf-8") as f:
        data = json.load(f)
    areas = []
    skipped = 0
    for feature in data["features"]:
        props = feature.get("properties") or {}
        district = props.get("district")
        section = props.get("section")
        geometry = feature.get("geometry")
        if not district or not section or not geometry:
            skipped += 1
            continue
        district = DISTRICT_NAME_ALIASES.get(district, district)
        areas.append((district, section, json.dumps(geometry)))
    return areas, skipped


def main(db_url, geojson_path, apply_changes, force):
    areas, skipped = load_areas(geojson_path)
    print(f"Полигонов в geojson: {len(areas)} (пропущено без district/section/geometry: {skipped})")

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    cur.execute("SELECT id, name FROM districts")
    district_id_by_name = {name: str(district_id) for district_id, name in cur.fetchall()}

    unknown_districts = sorted({d for d, _, _ in areas if d not in district_id_by_name})
    if unknown_districts:
        print("\nРайоны из geojson, не найденные в БД (их полигоны пропущены):")
        for d in unknown_districts:
            print(f"  {d!r}")

    areas_with_district = [
        (district_id_by_name[d], section, geom_json)
        for d, section, geom_json in areas
        if d in district_id_by_name
    ]

    cur.execute("CREATE TEMP TABLE areas_tmp (district_id uuid, section text, geom geometry(Geometry, 4326))")
    execute_values(
        cur,
        "INSERT INTO areas_tmp (district_id, section, geom) VALUES %s",
        areas_with_district,
        template="(%s::uuid, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))",
    )

    # ST_Intersects, не ST_Contains — центроид ровно на границе полигона
    # (частый случай для смежных дворовых участков) не должен теряться.
    # DISTINCT ON + ORDER BY ST_Area — если центроид неожиданно попал в
    # два перекрывающихся полигона, берём более точный (меньшей площади).
    cur.execute("""
        SELECT DISTINCT ON (s.id) s.id, s.courtyard_id, a.section
        FROM sites s
        JOIN courtyards c ON c.id = s.courtyard_id
        JOIN areas_tmp a ON a.district_id = c.district_id
            AND ST_Intersects(a.geom, ST_Centroid(s.geometry))
        WHERE s.is_active
        ORDER BY s.id, ST_Area(a.geom) ASC
    """)
    votes = defaultdict(Counter)
    for _site_id, courtyard_id, section in cur.fetchall():
        votes[courtyard_id][section] += 1

    cur.execute("""
        SELECT c.id, c.name, d.name, c.section, count(s.id) FILTER (WHERE s.is_active)
        FROM courtyards c
        JOIN districts d ON d.id = c.district_id
        LEFT JOIN sites s ON s.courtyard_id = c.id
        GROUP BY c.id, c.name, d.name, c.section
        ORDER BY d.name, c.name
    """)
    courtyards = cur.fetchall()

    to_update = []
    ambiguous = []
    no_active_sites = []
    no_polygon_match = []
    skipped_already_set = 0

    for courtyard_id, name, district_name, current_section, active_sites in courtyards:
        if current_section and not force:
            skipped_already_set += 1
            continue
        ranked = votes.get(courtyard_id, Counter()).most_common()
        if not ranked:
            (no_active_sites if not active_sites else no_polygon_match).append((name, district_name))
            continue
        top_section, top_count = ranked[0]
        if len(ranked) > 1 and ranked[1][1] == top_count:
            ambiguous.append((name, district_name, ranked))
            continue
        if current_section == top_section:
            continue
        to_update.append((courtyard_id, name, district_name, current_section, top_section))

    print(f"\nДворов всего: {len(courtyards)}")
    print(f"  уже с проставленным участком (пропущены, section не менялся): {skipped_already_set}")
    print(f"  без активных площадок: {len(no_active_sites)}")
    print(f"  с активными площадками, но ни одна не совпала с полигоном karta-sao: {len(no_polygon_match)}")
    print(f"  неоднозначно (голоса площадок разделились поровну): {len(ambiguous)}")
    print(f"  к изменению: {len(to_update)}")

    if no_polygon_match:
        print("\nНе удалось определить участок пространственно — разобрать вручную:")
        for name, district_name in no_polygon_match:
            print(f"  {district_name} / {name}")

    if ambiguous:
        print("\nНеоднозначно (нужна ручная проверка):")
        for name, district_name, ranked in ambiguous:
            votes_str = ", ".join(f"{sec}={cnt}" for sec, cnt in ranked)
            print(f"  {district_name} / {name}: {votes_str}")

    if to_update:
        print("\nБудет проставлено:")
        for _id, name, district_name, before, after in to_update:
            print(f"  {district_name} / {name}: {before or '—'} → {after}")

    if not to_update:
        print("\nМенять нечего.")
        conn.close()
        return

    if not apply_changes:
        print("\nЭто отчёт. Чтобы применить — повторите с --apply.")
        conn.close()
        return

    updated = 0
    for courtyard_id, _name, _district_name, before, after in to_update:
        cur.execute(
            "UPDATE courtyards SET section = %s WHERE id = %s AND section IS NOT DISTINCT FROM %s",
            (after, courtyard_id, before),
        )
        updated += cur.rowcount
    conn.commit()
    print(f"\nПроставлен участок {updated} дворам.")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db-url", required=True, help="строка подключения, напр. postgresql://postgres:пароль@db:5432/sao_inspection")
    parser.add_argument("--geojson", required=True, help="локальный путь к areas.geojson")
    parser.add_argument("--apply", action="store_true", help="реально проставить участки (без флага — только отчёт)")
    parser.add_argument("--force", action="store_true", help="пересчитать и дворы, у которых section уже задан")
    args = parser.parse_args()
    main(args.db_url, args.geojson, args.apply, args.force)
