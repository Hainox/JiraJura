# -*- coding: utf-8 -*-
"""Импорт KML в PostgreSQL/PostGIS: districts → courtyards → sites с геометрией.

Примеры:
  dev:  python import_kml.py \
          --db-url postgresql://postgres:postgres@localhost:5433/sao_inspection \
          --kml "KML_WGS84/Детская_площадка.kml=Детская площадка" \
          --kml "KML_WGS84/Спортивная_площадка.kml=Спортивная площадка" \
          --wipe
  prod: см. deploy/README.md, раздел «Импорт площадок из KML».
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import argparse
import xml.etree.ElementTree as ET
import re, math, psycopg2, traceback

NS = {'kml': 'http://www.opengis.net/kml/2.2'}


def parse_args():
    p = argparse.ArgumentParser(
        description='Импорт площадок из KML-выгрузок в БД JiraJura '
                    '(districts → courtyards → sites)')
    p.add_argument('--db-url', required=True,
                   help='строка подключения, напр. postgresql://postgres:пароль@db:5432/sao_inspection')
    p.add_argument('--kml', action='append', required=True, metavar='ФАЙЛ=ТИП',
                   help='путь к KML и тип площадки через "=", напр. '
                        '"Детская_площадка.kml=Детская площадка"; '
                        'параметр можно повторять для нескольких файлов')
    p.add_argument('--wipe', action='store_true',
                   help='обязательное подтверждение: перед импортом удаляются ВСЕ '
                        'площадки/дворы/районы и связанные обходы, замечания и фото')
    args = p.parse_args()

    args.kml_files = []
    for spec in args.kml:
        fname, sep, site_type = spec.partition('=')
        if not sep or not fname or not site_type:
            p.error(f'--kml ожидает формат ФАЙЛ=ТИП, получено: {spec!r}')
        args.kml_files.append((fname, site_type))
    return args


def parse_coords(text):
    pts = []
    for t in text.strip().split():
        p = t.split(',')
        if len(p) >= 2:
            pts.append((float(p[0]), float(p[1])))
    return pts


def centroid(pts):
    n = len(pts)
    return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)


def haversine(lon1, lat1, lon2, lat2):
    R = 6371000
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def wkt_polygon(pts):
    ring = ', '.join(f'{lon} {lat}' for lon, lat in pts)
    return f'POLYGON(({ring}))'


def parse_desc(text):
    d = {}
    for line in text.strip().split('\n'):
        if ':' in line:
            k, v = line.split(':', 1)
            d[k.strip()] = v.strip()
    return d


def main():
    args = parse_args()
    if not args.wipe:
        print('Импорт полностью замещает данные: будут удалены все площадки, дворы,')
        print('районы и связанные с ними обходы, замечания и фото. Если это')
        print('действительно нужно — повторите команду с флагом --wipe.')
        sys.exit(2)

    conn = psycopg2.connect(args.db_url)
    cur = conn.cursor()
    cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    cur.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ── Фаза 1: сбор ────────────────────────────────────────────
    # known:  (lon, lat, district, courtyard, area, site_type, cleaning, wkt, pm_name)  — 9 полей
    # unknown: (lon, lat, courtyard, area, site_type, cleaning, wkt, pm_name)            — 8 полей
    known = []
    unknown = []

    for fname, site_type in args.kml_files:
        print(f'Парсим: {fname}')
        tree = ET.parse(fname)
        doc = tree.find('.//kml:Document', NS)

        for folder in doc.findall('.//kml:Folder', NS):
            fn = folder.find('kml:name', NS)
            folder_name = fn.text if fn is not None else '?'
            m = re.match(r'(.+?)\s*\(\d+\)\s*$', folder_name)
            district = (m.group(1) if m else folder_name).strip()

            for pm in folder.findall('.//kml:Placemark', NS):
                n_tag = pm.find('kml:name', NS)
                d_tag = pm.find('kml:description', NS)
                pm_name = n_tag.text if n_tag is not None else '?'
                desc = d_tag.text if d_tag is not None else ''
                fields = parse_desc(desc)

                courtyard = fields.get('Двор', 'Не указан')
                cleaning = fields.get('Уборка', 'Ручная уборка')

                area = 0.0
                area_str = fields.get('Площадь', '0').replace(',', '.')
                m_a = re.search(r'[\d.]+', area_str)
                if m_a:
                    try:
                        area = float(m_a.group())
                    except ValueError:
                        area = 0.0

                outer = pm.find('.//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates', NS)
                if outer is None or not outer.text:
                    continue
                pts = parse_coords(outer.text)
                if len(pts) < 3:
                    continue

                c = centroid(pts)
                wkt = wkt_polygon(pts)
                rec = (courtyard, area, site_type, cleaning, wkt, pm_name)

                if district == 'без_района':
                    unknown.append((c[0], c[1]) + rec)
                else:
                    known.append((c[0], c[1], district) + rec)

    print(f'Известных (с районом): {len(known)}')
    print(f'Неизвестных (без района): {len(unknown)}')

    # ── Фаза 2: nearest-neighbour ────────────────────────────────
    print('Привязываем объекты без района...')
    for u_lon, u_lat, u_court, u_area, u_stype, u_cleaning, u_wkt, u_pmname in unknown:
        best_dist, best_district = float('inf'), None
        for k_lon, k_lat, k_district, *_ in known:
            d = haversine(u_lon, u_lat, k_lon, k_lat)
            if d < best_dist:
                best_dist = d
                best_district = k_district
        known.append((u_lon, u_lat, best_district, u_court, u_area, u_stype, u_cleaning, u_wkt, u_pmname))

    print(f'Всего объектов после привязки: {len(known)}')

    # ── Фаза 3: БД ──────────────────────────────────────────────
    print('Очищаем старые данные...')
    cur.execute("DELETE FROM issue_status_history")
    cur.execute("DELETE FROM issues")
    cur.execute("DELETE FROM checklist_answers")
    cur.execute("DELETE FROM inspections")
    cur.execute("DELETE FROM photos")
    cur.execute("DELETE FROM equipment")
    cur.execute("DELETE FROM sites")
    cur.execute("DELETE FROM courtyards")
    cur.execute("DELETE FROM districts")
    conn.commit()

    print('Загружаем районы...')
    district_names = sorted(set(r[2] for r in known))
    dist_map = {}
    for name in district_names:
        code = name.lower().replace(' ', '_')
        cur.execute("INSERT INTO districts (name, code) VALUES (%s, %s) RETURNING id", (name, code))
        dist_map[name] = cur.fetchone()[0]
    conn.commit()
    print(f'  Районов: {len(dist_map)}')

    print('Загружаем дворы...')
    pairs = sorted(set((r[2], r[3]) for r in known))
    court_map = {}
    for dist_name, court_name in pairs:
        cur.execute(
            "INSERT INTO courtyards (district_id, name) VALUES (%s, %s) "
            "ON CONFLICT (district_id, name) DO UPDATE SET name = EXCLUDED.name "
            "RETURNING id",
            (dist_map[dist_name], court_name)
        )
        court_map[(dist_name, court_name)] = cur.fetchone()[0]
    conn.commit()
    print(f'  Дворов: {len(court_map)}')

    print('Загружаем площадки...')
    count, skipped, batch = 0, 0, 0
    for lon, lat, district, courtyard, area, site_type, cleaning, wkt, pm_name in known:
        cid = court_map.get((district, courtyard))
        if cid is None:
            skipped += 1
            continue
        try:
            cur.execute(
                "INSERT INTO sites (courtyard_id, type, area_m2, cleaning_type, geometry, kml_original_id, is_active) "
                "VALUES (%s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s, TRUE)",
                (cid, site_type, area, cleaning, wkt, pm_name[:200])
            )
            count += 1
            batch += 1
            if batch >= 500:
                conn.commit()
                print(f'  ... {count}')
                batch = 0
        except Exception as e:
            print(f'  SKIP {pm_name[:60]}: {e}')
            conn.rollback()
            skipped += 1
            batch = 0

    conn.commit()
    print(f'Загружено площадок: {count}, пропущено: {skipped}')
    cur.close()
    conn.close()
    print('\n=== ИМПОРТ ЗАВЕРШЁН ===')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'\nОШИБКА: {e}')
        traceback.print_exc()
        sys.exit(1)
