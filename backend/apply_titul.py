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


# Канонизация сокращений: в KML адреса встречаются и в полной форме
# («улица Расковой дом 16, корпус 1»), и в сокращённой («Расковой ул. 16 к.1»).
_CANON = {
    "улица": "ул", "ул": "ул",
    "проспект": "просп", "просп": "просп", "пр-т": "просп",
    "проезд": "пр-д", "пр-д": "пр-д",
    "переулок": "пер", "пер": "пер",
    "бульвар": "б-р", "бульв": "б-р", "б-р": "б-р",
    "шоссе": "ш", "ш": "ш",
    "набережная": "наб", "наб": "наб",
    "площадь": "пл", "пл": "пл",
    "корпус": "к", "корп": "к", "к": "к",
    "строение": "с", "стр": "с", "с": "с",
    "владение": "вл", "вл": "вл",
}
_IGNORE = {"дом", "д", "г", "москва"}


def addr_key(s: str) -> tuple:
    """Ключ адреса, устойчивый к форме записи: регистр, ё, знаки препинания,
    сокращения типов улиц/корпусов, слово «дом» и порядок слов не влияют."""
    s = (s or "").lower().replace("ё", "е")
    for ch in ".,;":
        s = s.replace(ch, " ")
    tokens = []
    for t in s.split():
        t = _CANON.get(t, t)
        if t in _IGNORE:
            continue
        tokens.append(t)
    return tuple(sorted(tokens))


def main():
    p = argparse.ArgumentParser(description="Сверка площадок с перечнем ТИТУЛ")
    p.add_argument("--db-url", required=True)
    p.add_argument("--csv", required=True, help="CSV с колонками kml_id;district;type;address")
    p.add_argument("--apply", action="store_true",
                   help="применить изменения (без флага — только отчёт)")
    args = p.parse_args()

    want_ids = set()
    want_addr = set()   # (type, addr_key)
    csv_rows = 0
    with open(args.csv, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter=";"):
            csv_rows += 1
            if row["kml_id"]:
                want_ids.add(row["kml_id"].strip())
            want_addr.add((row["type"].strip(), addr_key(row["address"])))

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
        elif (stype, addr_key(court)) in want_addr:
            keep.append(sid)
            by_addr += 1
        else:
            drop.append((sid, district, stype, court, kml_id))

    print(f"Строк в перечне: {csv_rows} (с ID: {len(want_ids)})")
    print(f"Площадок в БД:  {len(sites)}")
    print(f"Остаются активными: {len(keep)}  (по ID: {by_id}, по адресу+типу: {by_addr})")
    print(f"Будут отключены:    {len(drop)}")
    if by_id == 0:
        print("Матчинг по ID не сработал (в KML другие идентификаторы) — "
              "сверка идёт по нормализованному адресу и типу.")

    # адреса из перечня, не нашедшие НИ одной площадки в БД
    db_keys = {(stype, addr_key(court)) for _, _, stype, court, _, _ in sites}
    absent = [a for a in want_addr if a not in db_keys]
    print(f"Адресов из перечня, отсутствующих в БД: {len(absent)} "
          f"(таких площадок не было в KML — завести автоматически нельзя)")
    for stype, key in absent[:10]:
        print(f"  {stype}: {' '.join(key)}")

    if drop:
        from collections import Counter
        print("\nОтключаемые по районам:")
        for district, cnt in sorted(Counter(d[1] for d in drop).items()):
            print(f"  {district}: {cnt}")
        print("\nПримеры отключаемых (первые 15):")
        for _, district, stype, court, kml_id in drop[:15]:
            print(f"  [{district}] {stype}: {court}")

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
