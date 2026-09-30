# -*- coding: utf-8 -*-
"""Загрузка перечня люков от округа в таблицу hatches (журнал осмотра люков).

Формат перечня заранее не известен, поэтому скрипт принимает Excel (.xlsx)
или CSV и сам находит нужные колонки по словам в заголовке («Адрес», «№
люка», «Владелец», «Широта»…). Какие колонки он распознал — печатается в
отчёте первым делом; если угадал неверно, колонку можно указать явно:
--col address="Адрес двора" --col number="Номер колодца".

Каждый люк привязывается к площадке (sites) по первому сработавшему способу:
  1. ID площадки из KML (колонка с kml-кодом площадки) — точно;
  2. координаты люка — площадка, внутри которой точка, иначе ближайшая
     площадка не дальше --max-distance метров (с учётом типа, если он указан);
  3. адрес — тот же нормализованный ключ, что и при сверке с ТИТУЛ
     (apply_titul.addr_key), с учётом типа и района, если они есть в перечне.
Строки, которые не удалось привязать однозначно, НЕ загружаются, а выводятся
в отчёт с причиной (а с --report-csv ещё и в файл — удобно вернуть округу).

Повторная загрузка безопасна: люк с тем же external_id (или той же парой
площадка+номер, если ID люка в перечне нет) обновляется, а не дублируется.
С --deactivate-missing люки, которых больше нет в перечне, выключаются
(is_active=FALSE, история осмотров сохраняется) — но только в районах, которые
есть в этом файле: перечень, присланный по одному району, не тронет остальные.

По умолчанию — только отчёт (dry-run). Запись в БД — с флагом --apply.

Запуск на сервере (файл кладём в /opt/jirajura/hatches/):
  docker compose -f docker-compose.prod.yml run --rm \\
    -v /opt/jirajura/hatches:/data:ro \\
    api python import_hatches.py --file /data/lyuki.xlsx
  … и то же самое с --apply
"""
import argparse
import csv
import os
import re
import sys
from collections import Counter, defaultdict

import psycopg2

from apply_titul import addr_key

SITE_TYPES = {
    "детская": "Детская площадка", "дп": "Детская площадка", "д": "Детская площадка",
    "спортивная": "Спортивная площадка", "сп": "Спортивная площадка", "с": "Спортивная площадка",
}

# Порядок важен: сначала более специфичные поля, чтобы «ID площадки» не ушло
# в external_id люка, а «Тип площадки» — в адрес.
FIELD_KEYWORDS = [
    ("external_id", ["id люка", "ид люка", "код люка", "уникальный номер люка"]),
    ("site_kml_id", ["id площадки", "ид площадки", "код площадки", "kml"]),
    ("site_type", ["тип площадки", "вид площадки", "тип"]),
    ("number", ["№ люка", "номер люка", "люк №", "номер колодца", "№ колодца", "номер", "№"]),
    ("owner", ["владелец", "балансодержатель", "принадлежность", "эксплуатирующ", "организация"]),
    ("location", ["место", "расположение", "описание", "примечание"]),
    ("lat", ["широта", "lat"]),
    ("lon", ["долгота", "lon", "lng"]),
    ("coords", ["координат"]),
    ("district", ["район"]),
    ("address", ["адрес площадки", "адрес двора", "адрес", "двор", "площадка"]),
]


def norm_header(h) -> str:
    s = str(h or "").strip().lower().replace("ё", "е")
    return re.sub(r"\s+", " ", s)


def detect_columns(headers, overrides):
    headers_n = [norm_header(h) for h in headers]
    mapping = {}
    used = set()
    for field, header in overrides.items():
        wanted = norm_header(header)
        if wanted not in headers_n:
            raise SystemExit(f"--col {field}: колонки «{header}» нет в файле. Есть: {headers}")
        mapping[field] = headers_n.index(wanted)
        used.add(mapping[field])
    for field, keywords in FIELD_KEYWORDS:
        if field in mapping:
            continue
        for kw in keywords:
            found = None
            for idx, h in enumerate(headers_n):
                if idx in used or not h:
                    continue
                # «№ п/п» — порядковый номер строки, а не номер люка
                if field == "number" and ("п/п" in h or "пп" == h):
                    continue
                if kw in h:
                    found = idx
                    break
            if found is not None:
                mapping[field] = found
                used.add(found)
                break
    return mapping


def read_table(path, sheet=None):
    """Строки файла как списки значений; первая строка, где распознано ≥2
    полей, считается заголовком (в выгрузках сверху часто шапка документа)."""
    if path.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb[sheet] if sheet else wb.worksheets[0]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
    else:
        raw = open(path, "rb").read()
        for enc in ("utf-8-sig", "cp1251"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise SystemExit("Не удалось прочитать CSV: ни UTF-8, ни Windows-1251")
        first = text.splitlines()[0] if text else ""
        delim = ";" if first.count(";") >= first.count(",") else ","
        rows = list(csv.reader(text.splitlines(), delimiter=delim))
    for i, row in enumerate(rows[:15]):
        if len(detect_columns(row, {})) >= 2:
            return rows[i], rows[i + 1:], i + 1
    raise SystemExit("Не нашёл строку заголовков в первых 15 строках файла")


def cell(row, mapping, field):
    idx = mapping.get(field)
    if idx is None or idx >= len(row):
        return ""
    v = row[idx]
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer() and field in ("number", "site_kml_id", "external_id"):
        v = int(v)
    return str(v).strip()


def parse_float(s):
    s = (s or "").strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_coords(row, mapping):
    lat = lon = None
    if "lat" in mapping and "lon" in mapping:
        lat, lon = parse_float(cell(row, mapping, "lat")), parse_float(cell(row, mapping, "lon"))
    elif "coords" in mapping:
        nums = re.findall(r"-?\d+(?:[.,]\d+)?", cell(row, mapping, "coords"))
        if len(nums) >= 2:
            lat, lon = parse_float(nums[0]), parse_float(nums[1])
    if lat is None or lon is None:
        return None
    # Москва: широта ~55–56, долгота ~37–38 — в выгрузках их нередко меняют местами
    if 36 < lat < 39 and 54 < lon < 57:
        lat, lon = lon, lat
    if not (54 < lat < 57 and 36 < lon < 39):
        return None
    return lat, lon


def parse_site_type(s):
    t = norm_header(s)
    if not t:
        return None
    for key, value in SITE_TYPES.items():
        if t == key or t.startswith(key):
            return value
    return None


def parse_overrides(items):
    out = {}
    for item in items or []:
        field, sep, header = item.partition("=")
        if not sep or not header:
            raise SystemExit(f"--col ожидает поле=Заголовок, получено: {item!r}")
        if field not in dict(FIELD_KEYWORDS):
            raise SystemExit(f"--col: неизвестное поле {field!r}. Поля: {', '.join(f for f, _ in FIELD_KEYWORDS)}")
        out[field] = header.strip().strip('"')
    return out


def load_sites(cur):
    cur.execute("""
        SELECT s.id, s.kml_original_id, s.type, c.name, d.name
        FROM sites s
        JOIN courtyards c ON c.id = s.courtyard_id
        JOIN districts d ON d.id = c.district_id
        WHERE s.is_active
    """)
    return cur.fetchall()


def match_by_point(cur, lat, lon, site_type, max_distance):
    type_sql = "AND s.type = %(type)s" if site_type else ""
    params = {"lat": lat, "lon": lon, "type": site_type, "dist": max_distance}
    cur.execute(f"""
        SELECT s.id FROM sites s
        WHERE s.is_active {type_sql}
          AND ST_Contains(s.geometry, ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326))
        LIMIT 2
    """, params)
    inside = [r[0] for r in cur.fetchall()]
    if len(inside) == 1:
        return inside[0], "координаты (внутри площадки)"
    cur.execute(f"""
        SELECT s.id,
               ST_Distance(s.geometry::geography,
                           ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography) AS dist
        FROM sites s
        WHERE s.is_active {type_sql}
          AND ST_DWithin(s.geometry::geography,
                         ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography, %(dist)s)
        ORDER BY dist
        LIMIT 2
    """, params)
    near = cur.fetchall()
    if not near:
        return None, f"нет площадки ближе {max_distance:g} м"
    # две площадки почти на одном расстоянии (детская и спортивная в одном
    # дворе) без указанного типа — не угадываем
    if len(near) == 2 and not site_type and abs(near[0][1] - near[1][1]) < 5:
        return None, "рядом две площадки на одинаковом расстоянии — укажите тип площадки"
    return near[0][0], f"координаты (ближайшая, {near[0][1]:.0f} м)"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--file", required=True, help="перечень люков: .xlsx или .csv")
    p.add_argument("--sheet", help="лист Excel (по умолчанию первый)")
    p.add_argument("--db-url", help="строка подключения; по умолчанию из DATABASE_URL")
    p.add_argument("--col", action="append", metavar="ПОЛЕ=Заголовок",
                   help="явно указать колонку, если автоопределение ошиблось")
    p.add_argument("--max-distance", type=float, default=60.0,
                   help="максимальное расстояние от люка до площадки, м (по умолчанию 60)")
    p.add_argument("--report-csv", help="записать непривязанные строки в этот CSV")
    p.add_argument("--deactivate-missing", action="store_true",
                   help="выключить люки, которых нет в перечне (только в районах из этого файла)")
    p.add_argument("--apply", action="store_true", help="записать в БД (без флага — только отчёт)")
    args = p.parse_args()

    db_url = args.db_url or os.environ.get("DATABASE_URL", "")
    db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    if not db_url:
        raise SystemExit("Укажите --db-url или переменную окружения DATABASE_URL")

    headers, rows, header_line = read_table(args.file, args.sheet)
    mapping = detect_columns(headers, parse_overrides(args.col))
    print(f"Файл: {args.file}, заголовок в строке {header_line}")
    print("Распознанные колонки:")
    for field, _ in FIELD_KEYWORDS:
        if field in mapping:
            print(f"  {field:<12} ← «{headers[mapping[field]]}»")
    if not ({"site_kml_id", "address", "coords"} & set(mapping) or {"lat", "lon"} <= set(mapping)):
        raise SystemExit("Не нашёл, по чему привязывать люки к площадкам: нужна колонка "
                         "с адресом, ID площадки или координатами. Укажите её через --col.")

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    sites = load_sites(cur)
    by_kml = defaultdict(list)
    by_addr = defaultdict(list)
    site_district = {sid: district for sid, _, _, _, district in sites}
    for sid, kml_id, stype, court, district in sites:
        if kml_id:
            by_kml[str(kml_id).strip()].append(sid)
        by_addr[addr_key(court)].append((sid, stype, district))

    matched, problems = [], []
    methods = Counter()
    for offset, row in enumerate(rows):
        line = header_line + 1 + offset
        if not any(str(v or "").strip() for v in row):
            continue
        address = cell(row, mapping, "address")
        site_type = parse_site_type(cell(row, mapping, "site_type"))
        district = cell(row, mapping, "district")
        point = parse_coords(row, mapping)
        site_id, how = None, None

        kml_id = cell(row, mapping, "site_kml_id")
        if kml_id and len(by_kml.get(kml_id, [])) == 1:
            site_id, how = by_kml[kml_id][0], "ID площадки"
        reason = None
        if site_id is None and point:
            site_id, how_or_reason = match_by_point(cur, point[0], point[1], site_type, args.max_distance)
            if site_id:
                how = how_or_reason
            else:
                reason = how_or_reason
        if site_id is None and address:
            cands = [c for c in by_addr.get(addr_key(address), [])
                     if (not site_type or c[1] == site_type)
                     and (not district or addr_key(c[2]) == addr_key(district.replace("ё", "е")))]
            if len(cands) == 1:
                site_id, how, reason = cands[0][0], "адрес", None
            elif len(cands) > 1:
                reason = "по адресу несколько площадок — укажите тип площадки или координаты"
            else:
                reason = reason or "площадка с таким адресом не найдена"
        if site_id is None:
            problems.append((line, address or "—", cell(row, mapping, "number") or "—",
                             reason or "нет ни адреса, ни ID площадки, ни координат"))
            continue
        methods[how.split(" (")[0]] += 1
        matched.append({
            "line": line, "site_id": site_id,
            "number": cell(row, mapping, "number"),
            "owner": cell(row, mapping, "owner") or None,
            "location": cell(row, mapping, "location") or None,
            "external_id": cell(row, mapping, "external_id") or None,
            "point": point,
        })

    # Номер люка обязателен и уникален в пределах площадки: пустые номера
    # проставляем по порядку, повторы внутри файла отбрасываем в отчёт.
    cur.execute("SELECT site_id, number FROM hatches")
    taken = defaultdict(set)
    for sid, num in cur.fetchall():
        taken[sid].add(num)
    seen = set()
    auto_numbered = 0
    final = []
    for h in matched:
        if not h["number"]:
            n = 1
            while str(n) in taken[h["site_id"]] or (h["site_id"], str(n)) in seen:
                n += 1
            h["number"] = str(n)
            auto_numbered += 1
        key = (h["site_id"], h["number"])
        if key in seen:
            problems.append((h["line"], "—", h["number"], "повтор: этот номер люка на этой площадке уже есть выше в файле"))
            continue
        seen.add(key)
        final.append(h)

    print(f"\nСтрок с данными: {len(matched) + len([p for p in problems if 'повтор' not in p[3]])}")
    print(f"Привязано к площадкам: {len(final)}  " + ", ".join(f"{k}: {v}" for k, v in methods.items()))
    if auto_numbered:
        print(f"Без номера люка (пронумерованы по порядку): {auto_numbered}")
    print(f"Не загружено (см. ниже): {len(problems)}")
    per_site = Counter(h["site_id"] for h in final)
    print(f"Площадок, где появятся люки: {len(per_site)}")

    if problems:
        print("\nНе загружены — нужно уточнить у округа:")
        for line, address, number, reason in problems[:200]:
            print(f"  строка {line}: {address}, люк {number} — {reason}")
        if len(problems) > 200:
            print(f"  … и ещё {len(problems) - 200}")
        if args.report_csv:
            with open(args.report_csv, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["Строка файла", "Адрес", "№ люка", "Причина"])
                w.writerows(problems)
            print(f"Список сохранён в {args.report_csv}")

    to_deactivate = []
    if args.deactivate_missing:
        keep_ext = {h["external_id"] for h in final if h["external_id"]}
        keep_pairs = {(h["site_id"], h["number"]) for h in final}
        covered = {site_district.get(h["site_id"]) for h in final}
        cur.execute("SELECT id, site_id, number, external_id FROM hatches WHERE is_active")
        for hid, sid, num, ext in cur.fetchall():
            if site_district.get(sid) not in covered:
                continue
            if (ext and ext in keep_ext) or (sid, num) in keep_pairs:
                continue
            to_deactivate.append(hid)
        print(f"\nБудет выключено люков, которых нет в перечне "
              f"(районы: {', '.join(sorted(d for d in covered if d))}): {len(to_deactivate)}")

    if not args.apply:
        print("\nЭто был dry-run — БД не изменена. Для записи добавьте --apply.")
        conn.close()
        return

    inserted = updated = failed = 0
    for h in final:
        point_sql = "ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)" if h["point"] else "NULL"
        params = {
            "site_id": h["site_id"], "number": h["number"], "owner": h["owner"],
            "location": h["location"], "external_id": h["external_id"],
            "lat": h["point"][0] if h["point"] else None, "lon": h["point"][1] if h["point"] else None,
        }
        conflict = "(external_id)" if h["external_id"] else "(site_id, number)"
        cur.execute("SAVEPOINT h")
        try:
            cur.execute(f"""
                INSERT INTO hatches (site_id, number, owner, location_note, point, external_id, is_active)
                VALUES (%(site_id)s, %(number)s, %(owner)s, %(location)s, {point_sql}, %(external_id)s, TRUE)
                ON CONFLICT {conflict} DO UPDATE SET
                    site_id = EXCLUDED.site_id,
                    number = EXCLUDED.number,
                    owner = COALESCE(EXCLUDED.owner, hatches.owner),
                    location_note = COALESCE(EXCLUDED.location_note, hatches.location_note),
                    point = COALESCE(EXCLUDED.point, hatches.point),
                    is_active = TRUE
                RETURNING (xmax = 0)
            """, params)
            if cur.fetchone()[0]:
                inserted += 1
            else:
                updated += 1
            cur.execute("RELEASE SAVEPOINT h")
        except psycopg2.IntegrityError as e:
            cur.execute("ROLLBACK TO SAVEPOINT h")
            failed += 1
            print(f"  строка {h['line']}: не записана — {e.pgerror.strip() if e.pgerror else e}")
    if to_deactivate:
        cur.execute("UPDATE hatches SET is_active = FALSE WHERE id = ANY(%s::uuid[])",
                    ([str(i) for i in to_deactivate],))
    conn.commit()
    print(f"\nГотово: добавлено {inserted}, обновлено {updated}, выключено {len(to_deactivate)}, ошибок {failed}.")
    conn.close()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(f"ОШИБКА: {e}", file=sys.stderr)
        raise
