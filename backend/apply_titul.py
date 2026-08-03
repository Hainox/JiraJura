# -*- coding: utf-8 -*-
"""Сверка площадок в БД с актуальным перечнем (лист ТИТУЛ) и отключение лишних.

Матчинг первично по ID из KML (sites.kml_original_id == kml_id из CSV);
для строк CSV без ID и несматченных по ID — запасной матчинг по
(тип, адрес двора). Площадки БД, не попавшие в перечень, помечаются
is_active=FALSE (не удаляются — история обходов сохраняется).

По умолчанию — только отчёт (dry-run). Применение — с флагом --apply.

Примеры:
  dry-run: python apply_titul.py --db-url postgresql://... --csv titul_2026-08.csv
  апплай:  python apply_titul.py --db-url postgresql://... --csv titul_2026-08.csv --apply
"""
import argparse
import csv
import sys

import psycopg2


def norm(s: str) -> str:
    """Нормализация адреса для запасного матчинга: регистр, ё, пробелы."""
    return " ".join((s or "").lower().replace("ё", "е").split())


def main():
    p = argparse.ArgumentParser(description="Сверка площадок с перечнем ТИТУЛ")
    p.add_argument("--db-url", required=True)
    p.add_argument("--csv", required=True, help="CSV с колонками kml_id;district;type;address")
    p.add_argument("--apply", action="store_true",
                   help="применить изменения (без флага — только отчёт)")
    args = p.parse_args()

    want_ids = set()
    want_addr = set()   # (type, normalized address)
    csv_rows = 0
    with open(args.csv, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter=";"):
            csv_rows += 1
            if row["kml_id"]:
                want_ids.add(row["kml_id"].strip())
            want_addr.add((row["type"].strip(), norm(row["address"])))

    conn = psycopg2.connect(args.db_url)
    cur = conn.cursor()
    cur.execute("""
        SELECT s.id, s.kml_original_id, s.type, c.name, d.name, s.is_active
        FROM sites s
        JOIN courtyards c ON c.id = s.courtyard_id
        JOIN districts d ON d.id = c.district_id
    """)
    sites = cur.fetchall()

    keep, drop = [], []
    matched_ids = set()
    by_id = by_addr = 0
    for sid, kml_id, stype, court, district, is_active in sites:
        kml_id = (kml_id or "").strip()
        if kml_id in want_ids:
            keep.append(sid)
            matched_ids.add(kml_id)
            by_id += 1
        elif (stype, norm(court)) in want_addr:
            keep.append(sid)
            by_addr += 1
        else:
            drop.append((sid, district, stype, court, kml_id))

    print(f"Строк в перечне: {csv_rows} (с ID: {len(want_ids)})")
    print(f"Площадок в БД:  {len(sites)}")
    print(f"Остаются активными: {len(keep)}  (по ID: {by_id}, по адресу+типу: {by_addr})")
    print(f"Будут отключены:    {len(drop)}")
    missing = want_ids - matched_ids
    print(f"ID из перечня, не найденные в БД: {len(missing)} "
          f"(таких площадок нет в KML-выгрузке — завести их автоматически нельзя)")

    if drop:
        print("\nПримеры отключаемых (первые 15):")
        for _, district, stype, court, kml_id in drop[:15]:
            print(f"  [{district}] {stype}: {court} (kml_id={kml_id or '—'})")

    if not args.apply:
        print("\nЭто был dry-run — БД не изменена. Для применения добавьте --apply.")
        return

    cur.execute("UPDATE sites SET is_active = FALSE")
    keep_ids = [str(s) for s in keep]
    cur.execute("UPDATE sites SET is_active = TRUE WHERE id = ANY(%s::uuid[])", (keep_ids,))
    conn.commit()
    cur.execute("SELECT is_active, count(*) FROM sites GROUP BY is_active")
    print("\nПрименено. Итог по is_active:", dict(cur.fetchall()))
    cur.close()
    conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ОШИБКА: {e}", file=sys.stderr)
        raise
