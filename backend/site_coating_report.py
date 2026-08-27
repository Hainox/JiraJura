# -*- coding: utf-8 -*-
"""Вид покрытия по каждой площадке — по запросу для доклада ДМ (штаб
26.08.2026): в JiraJura такого поля нет вообще (ни в Site, ни в KML-
импорте) — материал покрытия туда никогда не завозился. Пользователь
указал источник: карта https://hainox.github.io/karta-sao/ (репозиторий
Hainox/karta-sao, файлы dp.geojson/sp.geojson) — там у каждой площадки
есть свойство "site_type", которое на самом деле означает материал
покрытия (пример: "Резиновая крошка", "Асфальтобетонное", "Песчаное").

В JiraJura и на karta-sao нет общего стабильного ID площадки (kml_original_id
у нас — это имя Placemark из своего KML, а parent_id на карте — внешний
номер объекта из реестра, это разные вещи) — поэтому сопоставление здесь
ГЕОГРАФИЧЕСКОЕ: для каждой площадки JiraJura ищем ближайшую точку на карте
того же типа (детская/спортивная) в том же районе и берём её покрытие,
если расстояние меньше --max-distance (по умолчанию 40 м — типичный размер
площадки; дальше это уже физически другой объект). Это эвристика, не
гарантированная привязка по ID — расхождения возможны, особенно там, где
несколько площадок стоят кучно в одном дворе. Перед докладом стоит
выборочно свериться с картой по паре строк.

Числа не выдумываются: где ближайшая точка на карте дальше порога или её
вообще нет (тип/район не нашёлся на карте), площадка помечается явно
"не сопоставлено" — не подставляется случайное ближайшее покрытие.

Самодостаточный, как list_maf_deadlines.py/reissue_invites.py — не
импортирует app.models, только читает БД напрямую (плюс urllib для
загрузки geojson с карты, без новых зависимостей).

Запуск на сервере:
  # все площадки округа, только консоль:
  docker compose -f docker-compose.prod.yml exec api python site_coating_report.py

  # выгрузка в CSV (обязательно вне uploads/ — см. safe_export.py):
  docker compose -f docker-compose.prod.yml exec api python site_coating_report.py --out /app/exports/coating.csv

  # только один район:
  docker compose -f docker-compose.prod.yml exec api python site_coating_report.py --district "Ховрино" --out /app/exports/coating_hovrino.csv

  # отдельно детские / отдельно спортивные площадки — для доклада с разбивкой:
  docker compose -f docker-compose.prod.yml exec api python site_coating_report.py --site-type "Детская площадка" --out /app/exports/coating_detskie.csv
  docker compose -f docker-compose.prod.yml exec api python site_coating_report.py --site-type "Спортивная площадка" --out /app/exports/coating_sportivnye.csv

  # если у контейнера нет доступа в интернет — скачать dp.geojson/sp.geojson
  # заранее (например, git clone karta-sao на хосте и docker cp) и указать
  # локальные пути:
  docker compose -f docker-compose.prod.yml exec api python site_coating_report.py \
      --dp-geojson /app/exports/dp.geojson --sp-geojson /app/exports/sp.geojson
"""
import argparse
import asyncio
import csv
import json
import math
import os
import urllib.request

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/sao_inspection")

RAW_BASE = "https://raw.githubusercontent.com/Hainox/karta-sao/main"
GEOJSON_BY_TYPE = {
    "Детская площадка": ("dp.geojson", f"{RAW_BASE}/dp.geojson"),
    "Спортивная площадка": ("sp.geojson", f"{RAW_BASE}/sp.geojson"),
}
DEFAULT_MAX_DISTANCE_M = 40.0


def haversine(lon1, lat1, lon2, lat2):
    R = 6371000
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def load_candidates(site_type: str, local_path: str | None) -> dict:
    """Возвращает {район: [(lon, lat, покрытие, адрес), ...]} для типа площадки."""
    default_name, url = GEOJSON_BY_TYPE[site_type]
    if local_path:
        with open(local_path, encoding="utf-8") as f:
            data = json.load(f)
    else:
        print(f"  Загружаем {default_name} с карты ({url})...")
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

    by_district: dict = {}
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        geom = feature.get("geometry", {})
        if geom.get("type") != "Point":
            continue
        lon, lat = geom["coordinates"][0], geom["coordinates"][1]
        district = props.get("district", "?")
        coating = props.get("site_type", "не указано")
        address = props.get("address", props.get("name", "?"))
        by_district.setdefault(district, []).append((lon, lat, coating, address))
    return by_district


def nearest_coating(lon, lat, candidates, max_distance_m):
    best_dist, best = float("inf"), None
    for c_lon, c_lat, coating, address in candidates:
        d = haversine(lon, lat, c_lon, c_lat)
        if d < best_dist:
            best_dist, best = d, (coating, address)
    if best is None or best_dist > max_distance_m:
        return None, best_dist if best is not None else None
    return best, best_dist


async def main(district: str | None, out: str | None, max_distance: float,
                dp_geojson: str | None, sp_geojson: str | None, site_type: str | None):
    if out:
        from app.services.safe_export import reject_uploads_path, ensure_parent_dir
        reject_uploads_path(out)
        ensure_parent_dir(out)

    print("Загружаем карту покрытий...")
    # При --site-type грузим только нужный geojson — не гоняем лишний запрос
    # к карте, если, например, нужны только спортивные площадки.
    types_needed = [site_type] if site_type else list(GEOJSON_BY_TYPE)
    candidates_by_type = {t: load_candidates(t, dp_geojson if t == "Детская площадка" else sp_geojson)
                           for t in types_needed}

    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    params: dict = {}
    clauses = ["s.is_active = TRUE"]
    if district:
        clauses.append("d.name ILIKE :district")
        params["district"] = f"%{district}%"
    if site_type:
        clauses.append("s.type = :site_type")
        params["site_type"] = site_type
    where = " AND ".join(clauses)

    async with Session() as db:
        rows = (await db.execute(text(
            "SELECT d.name AS district_name, c.name AS courtyard_name, s.id AS site_id, "
            "s.type AS site_type, ST_X(s.centroid) AS lon, ST_Y(s.centroid) AS lat "
            "FROM sites s "
            "JOIN courtyards c ON c.id = s.courtyard_id "
            "JOIN districts d ON d.id = c.district_id "
            f"WHERE {where} "
            "ORDER BY d.name, c.name"
        ), params)).fetchall()

    if not rows:
        print(f"Площадок{' (' + site_type + ')' if site_type else ''} "
              f"{'в районе «' + district + '»' if district else 'по всем районам'} не найдено.")
        return

    fieldnames = ["Район", "Двор", "Тип площадки", "Вид покрытия", "Адрес на карте",
                  "Расстояние до точки на карте, м", "Комментарий"]

    def row_dict(r):
        candidates = candidates_by_type.get(r.site_type, {}).get(r.district_name, [])
        match, dist = nearest_coating(r.lon, r.lat, candidates, max_distance)
        if match is None:
            coating, address = "не сопоставлено", ""
            comment = (
                "нет площадок этого типа на карте в этом районе" if dist is None
                else f"ближайшая точка на карте дальше {max_distance:.0f} м ({dist:.0f} м)"
            )
        else:
            coating, address = match
            comment = ""
        return {
            "Район": r.district_name,
            "Двор": r.courtyard_name,
            "Тип площадки": r.site_type,
            "Вид покрытия": coating,
            "Адрес на карте": address,
            "Расстояние до точки на карте, м": f"{dist:.0f}" if dist is not None else "",
            "Комментарий": comment,
        }

    results = [row_dict(r) for r in rows]
    matched = sum(1 for r in results if r["Вид покрытия"] != "не сопоставлено")

    if out:
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            for r in results:
                writer.writerow(r)
        print(f"Площадок: {len(results)}, сопоставлено с картой: {matched} "
              f"({matched * 100 // len(results)}%). Сохранено в {out}")
    else:
        current_district = None
        for r in results:
            if r["Район"] != current_district:
                current_district = r["Район"]
                print(f"\n=== {current_district} ===")
            mark = "" if r["Вид покрытия"] != "не сопоставлено" else " ⚠"
            print(f"  {r['Двор']} ({r['Тип площадки']}) — {r['Вид покрытия']}{mark}"
                  + (f"  [{r['Комментарий']}]" if r["Комментарий"] else ""))
        print(f"\nВсего: {len(results)} площадок, сопоставлено с картой: {matched} "
              f"({matched * 100 // len(results)}%).")
        if matched < len(results):
            print("Несопоставленные помечены ⚠ — покрытие для них в отчёт не подставлялось.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--district", help="фильтр по району (частичное совпадение)")
    parser.add_argument("--out", help="путь к CSV (вне uploads/); без этого флага — только вывод в консоль")
    parser.add_argument("--max-distance", type=float, default=DEFAULT_MAX_DISTANCE_M,
                         help=f"порог сопоставления в метрах (по умолчанию {DEFAULT_MAX_DISTANCE_M:.0f})")
    parser.add_argument("--dp-geojson", help="локальный путь к dp.geojson вместо загрузки с карты")
    parser.add_argument("--sp-geojson", help="локальный путь к sp.geojson вместо загрузки с карты")
    parser.add_argument("--site-type", choices=["Детская площадка", "Спортивная площадка"], default=None,
                         help="фильтр по типу площадки (по умолчанию — детские и спортивные вместе)")
    args = parser.parse_args()
    asyncio.run(main(args.district, args.out, args.max_distance, args.dp_geojson, args.sp_geojson, args.site_type))
