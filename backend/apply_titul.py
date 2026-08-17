# -*- coding: utf-8 -*-
"""Сверка площадок в БД с актуальным перечнем (лист ТИТУЛ): строго 1:1.

Каждая строка перечня получает ровно одну площадку БД (сначала по ID из
KML, затем по точному нормализованному адресу+типу, затем по частичному
совпадению адреса). Площадки БД, не получившие строки перечня, помечаются
is_active=FALSE (не удаляются — история обходов сохраняется). Таким
образом активных площадок становится ровно столько, скольким строкам
перечня нашлась пара; строки без пары перечисляются в отчёте отдельно.

При выборе, какая из одинаковых по адресу площадок останется активной,
приоритет у площадок с уже проведёнными обходами.

По умолчанию — только отчёт (dry-run). Применение — с флагом --apply.

Примеры:
  dry-run: python apply_titul.py --db-url postgresql://... --csv titul_2026-08.csv
  апплай:  python apply_titul.py --db-url postgresql://... --csv titul_2026-08.csv --apply
"""
import argparse
import csv
import sys
from collections import Counter, defaultdict, deque

import psycopg2


# Канонизация сокращений: в KML адреса встречаются и в полной форме
# («улица Расковой дом 16, корпус 1»), и в сокращённой («Расковой ул. 16 к.1»).
_CANON = {
    "улица": "ул", "ул": "ул",
    # «пр.» в перечне используется и для проезда, и встречается для проспекта —
    # сводим проспект/проезд в один токен: ложное равенство «X проспект»==«X проезд»
    # требует существования обеих улиц с одним именем (в САО таких нет), а
    # ложное РАЗЛИЧИЕ из-за «пр.» уже приводило к ошибочному отключению площадок
    "проспект": "пр", "просп": "пр", "пр-т": "пр",
    "проезд": "пр", "пр-д": "пр", "пр": "пр",
    "переулок": "пер", "пер": "пер",
    # «Большая/Малая» в перечне сокращаются до «Б./М.» (Академическая Б. ул.)
    "большая": "б", "б": "б",
    "малая": "м", "м": "м",
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
    p = argparse.ArgumentParser(description="Сверка площадок с перечнем ТИТУЛ (1:1)")
    p.add_argument("--db-url", required=True)
    p.add_argument("--csv", required=True, help="CSV с колонками kml_id;district;type;address")
    p.add_argument("--apply", action="store_true",
                   help="применить изменения (без флага — только отчёт)")
    args = p.parse_args()

    reg_rows = []
    with open(args.csv, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter=";"):
            reg_rows.append({
                "kml_id": (row["kml_id"] or "").strip(),
                "district": (row["district"] or "").strip(),
                "type": (row["type"] or "").strip(),
                "address": (row["address"] or "").strip(),
                "key": addr_key(row["address"]),
                "site": None,
            })

    conn = psycopg2.connect(args.db_url)
    cur = conn.cursor()
    # площадки с уже проведёнными обходами разбирают слоты первыми; среди
    # них — площадки с обходом, который прямо сейчас не завершён (kто-то
    # реально ходит по ней в поле) в первую очередь. Без has_active_insp
    # площадка с одним старым обходом и площадка, по которой инспектор
    # СЕЙЧАС идёт (но обходов у неё пока накопилось меньше), сравнивались
    # только по insp_cnt — вторую могло отключить, осиротив текущий обход
    # (is_active=FALSE прячет площадку из GET /sites/, а сам Inspection не
    # удаляется — инспектор физически не находит, чем завершить обход).
    cur.execute("""
        SELECT s.id, s.kml_original_id, s.type, c.name, d.name,
               (SELECT count(*) FROM inspections i WHERE i.site_id = s.id) AS insp_cnt,
               EXISTS (
                   SELECT 1 FROM inspections i
                   WHERE i.site_id = s.id AND i.status IN ('planned', 'in_progress')
               ) AS has_active_insp
        FROM sites s
        JOIN courtyards c ON c.id = s.courtyard_id
        JOIN districts d ON d.id = c.district_id
        ORDER BY has_active_insp DESC, insp_cnt DESC, s.id
    """)
    sites = cur.fetchall()

    by_id_idx = defaultdict(deque)
    exact_idx = defaultdict(deque)
    for i, r in enumerate(reg_rows):
        if r["kml_id"]:
            by_id_idx[r["kml_id"]].append(i)
        exact_idx[(r["type"], r["key"])].append(i)

    def pop_free(dq):
        while dq:
            i = dq.popleft()
            if reg_rows[i]["site"] is None:
                return i
        return None

    by_id = by_addr = by_subset = 0

    # этап 1: точное совпадение ID из KML
    unpaired = []
    for s in sites:
        sid, kml_id, stype, court, district, insp, has_active = s
        i = pop_free(by_id_idx.get((kml_id or "").strip(), deque()))
        if i is not None:
            reg_rows[i]["site"] = s
            by_id += 1
        else:
            unpaired.append(s)

    # этап 2: точный нормализованный адрес + тип
    still = []
    for s in unpaired:
        sid, kml_id, stype, court, district, insp, has_active = s
        i = pop_free(exact_idx.get((stype, addr_key(court)), deque()))
        if i is not None:
            reg_rows[i]["site"] = s
            by_addr += 1
        else:
            still.append(s)

    # этап 3: частичное совпадение — строка перечня может покрывать несколько
    # домов, а в БД это отдельные дворы (и наоборот); совпадение, если токены
    # одного адреса являются подмножеством другого (в рамках типа)
    free_by_type = defaultdict(list)
    for i, r in enumerate(reg_rows):
        if r["site"] is None:
            free_by_type[r["type"]].append(i)

    drop = []
    for s in still:
        sid, kml_id, stype, court, district, insp, has_active = s
        c = Counter(addr_key(court))
        found = None
        for i in free_by_type.get(stype, ()):
            r = reg_rows[i]
            if r["site"] is not None:
                continue
            w = Counter(r["key"])
            if not (c - w) or not (w - c):
                found = i
                break
        if found is not None:
            reg_rows[found]["site"] = s
            by_subset += 1
        else:
            drop.append(s)

    matched = [r for r in reg_rows if r["site"] is not None]
    unmatched = [r for r in reg_rows if r["site"] is None]
    keep_ids = [str(r["site"][0]) for r in matched]

    print(f"Строк в перечне:  {len(reg_rows)}")
    print(f"Площадок в БД:    {len(sites)}")
    print(f"Сопоставлено 1:1: {len(matched)}  "
          f"(по ID: {by_id}, по точному адресу: {by_addr}, по частичному: {by_subset})")
    print(f"Будут отключены:  {len(drop)} (дубли адресов и отсутствующие в перечне)")
    print(f"Строк перечня без пары в БД: {len(unmatched)}")
    print(f"=> после применения активных будет {len(matched)} "
          f"(= {len(reg_rows)} − {len(unmatched)})")

    if unmatched:
        print("\nСтроки перечня без пары (этих площадок нет в KML-выгрузке, "
              "нужны геоданные, чтобы завести):")
        for r in unmatched:
            print(f"  [{r['district']}] {r['type']}: {r['address']}")

    if drop:
        print("\nОтключаемые по районам:")
        for district, cnt in sorted(Counter(s[4] for s in drop).items()):
            print(f"  {district}: {cnt}")
        drop_with_hist = [s for s in drop if s[5]]
        if drop_with_hist:
            print(f"\n⚠ Отключаемых с уже проведёнными обходами: {len(drop_with_hist)}")
            for sid, _, stype, court, district, insp, has_active in drop_with_hist[:10]:
                print(f"  [{district}] {stype}: {court} (обходов: {insp})")
        drop_with_active = [s for s in drop if s[6]]
        if drop_with_active:
            print(f"\n⚠⚠ Отключаемых с НЕЗАВЕРШЁННЫМ обходом прямо сейчас: {len(drop_with_active)} "
                  f"— инспектор потеряет доступ к своему текущему обходу:")
            for sid, _, stype, court, district, insp, has_active in drop_with_active:
                print(f"  [{district}] {stype}: {court}")
        print("\nПримеры отключаемых (первые 15):")
        for sid, kml_id, stype, court, district, insp, has_active in drop[:15]:
            print(f"  [{district}] {stype}: {court}")

    if not args.apply:
        print("\nЭто был dry-run — БД не изменена. Для применения добавьте --apply.")
        return

    cur.execute("UPDATE sites SET is_active = FALSE")
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
