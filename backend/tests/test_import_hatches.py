"""Загрузка окружного перечня люков (import_hatches.py): автоопределение
колонок, привязка к площадкам по координатам / адресу / ID площадки,
dry-run по умолчанию и идемпотентная повторная загрузка.

У каждого теста свои площадки в уникальной точке карты и с уникальным
адресом — общая тестовая БД содержит площадки соседних тестов, и привязка
по координатам не должна на них попадать.
"""
import os
import random
import sys
import uuid

import psycopg2
import pytest
from openpyxl import Workbook

import import_hatches

SYNC_DB_URL = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")


def _exec(sql, params=None):
    with psycopg2.connect(SYNC_DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or {})


def _all(sql, params=None):
    with psycopg2.connect(SYNC_DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or {})
            return cursor.fetchall()


def _district() -> tuple[str, str]:
    district_id = str(uuid.uuid4())
    name = f"Импорт {district_id[:8]}"
    _exec("INSERT INTO districts(id,name,code) VALUES (%s,%s,%s)", (district_id, name, district_id[:8]))
    return district_id, name


def _site(district_id: str, address: str, site_type: str = "Детская площадка", kml_id: str | None = None):
    """Площадка-квадрат ~50 м в случайной точке Москвы; возвращает id и
    координаты её центра (lat, lon). Двор с таким адресом в районе
    переиспользуется — как в жизни, детская и спортивная в одном дворе."""
    lon = 37.35 + random.random() * 0.4
    lat = 55.62 + random.random() * 0.25
    d = 0.0005
    polygon = f"POLYGON(({lon} {lat},{lon + d} {lat},{lon + d} {lat + d},{lon} {lat + d},{lon} {lat}))"
    site_id = str(uuid.uuid4())
    _exec(
        "INSERT INTO courtyards(id,district_id,name) VALUES (%s,%s,%s) "
        "ON CONFLICT (district_id, name) DO NOTHING",
        (str(uuid.uuid4()), district_id, address),
    )
    _exec(
        "INSERT INTO sites(id,courtyard_id,type,area_m2,geometry,is_active,kml_original_id) "
        "VALUES (%s,(SELECT id FROM courtyards WHERE district_id=%s AND name=%s),%s,100,"
        "ST_GeomFromText(%s,4326),true,%s)",
        (site_id, district_id, address, site_type, polygon, kml_id),
    )
    return site_id, (lat + d / 2, lon + d / 2)


def _run(*argv, capsys=None):
    old = sys.argv
    sys.argv = ["import_hatches.py", "--db-url", SYNC_DB_URL, *argv]
    try:
        import_hatches.main()
    finally:
        sys.argv = old
    return capsys.readouterr().out if capsys else ""


def _hatches(site_id):
    return _all(
        "SELECT number, owner, location_note, external_id, is_active, "
        "ST_Y(point), ST_X(point) FROM hatches WHERE site_id = %s ORDER BY number",
        (site_id,),
    )


def _write_csv(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def test_csv_matches_by_coordinates_and_address_dry_run_then_apply(tmp_path, capsys):
    district_id, district = _district()
    street = f"Люковая{uuid.uuid4().hex[:6]}"
    by_point, center = _site(district_id, f"{street} ул. 1")
    by_address, _ = _site(district_id, f"{street} ул. 2 к.1")
    csv_path = _write_csv(tmp_path / "lyuki.csv", [
        "Перечень люков на детских и спортивных площадках;;;;;",
        "№ п/п;Адрес площадки;№ люка;Владелец;Широта;Долгота",
        # координаты с запятой и перепутанные местами — частый вид выгрузок
        f"1;;1;Мосводоканал;{str(center[1]).replace('.', ',')};{str(center[0]).replace('.', ',')}",
        f"2;{street} улица дом 2 корпус 1;;МОЭК;;",
        f"3;{street} ул. 99;1;Связь;;",
    ])

    out = _run("--file", csv_path, capsys=capsys)
    assert "address      ← «Адрес площадки»" in out
    assert "number       ← «№ люка»" in out
    assert "Привязано к площадкам: 2" in out
    assert "площадка с таким адресом не найдена" in out
    assert "dry-run" in out
    assert _hatches(by_point) == [] and _hatches(by_address) == []

    _run("--file", csv_path, "--apply", capsys=capsys)
    [h1] = _hatches(by_point)
    assert h1[:5] == ("1", "Мосводоканал", None, None, True)
    assert h1[5] == pytest.approx(center[0]) and h1[6] == pytest.approx(center[1])
    # без номера в перечне — пронумерован по порядку
    assert _hatches(by_address)[0][:2] == ("1", "МОЭК")


def test_reimport_updates_instead_of_duplicating(tmp_path, capsys):
    district_id, _ = _district()
    street = f"Повторная{uuid.uuid4().hex[:6]}"
    site_id, _ = _site(district_id, f"{street} ул. 5")
    first = _write_csv(tmp_path / "a.csv", ["Адрес;Номер люка;Владелец", f"{street} ул. 5;3;МОЭК"])
    _run("--file", first, "--apply", capsys=capsys)
    second = _write_csv(tmp_path / "b.csv", ["Адрес;Номер люка;Владелец;Примечание",
                                            f"{street} ул. 5;3;Мосводоканал;у песочницы"])
    out = _run("--file", second, "--apply", capsys=capsys)
    assert "добавлено 0, обновлено 1" in out
    assert [h[:3] for h in _hatches(site_id)] == [("3", "Мосводоканал", "у песочницы")]


def test_xlsx_with_site_kml_id_and_external_id(tmp_path, capsys):
    district_id, _ = _district()
    kml_id = f"kml{uuid.uuid4().hex[:8]}"
    site_id, _ = _site(district_id, f"Экселева{uuid.uuid4().hex[:6]} ул. 7",
                       site_type="Спортивная площадка", kml_id=kml_id)
    wb = Workbook()
    ws = wb.active
    ws.append(["ID площадки", "ID люка", "Номер люка", "Балансодержатель"])
    ext = f"L-{uuid.uuid4().hex[:8]}"
    ws.append([kml_id, ext, 2, "МГТС"])
    path = tmp_path / "lyuki.xlsx"
    wb.save(path)

    _run("--file", str(path), "--apply", capsys=capsys)
    assert [h[:4] for h in _hatches(site_id)] == [("2", "МГТС", None, ext)]


def test_same_address_two_site_types_needs_type_column(tmp_path, capsys):
    district_id, _ = _district()
    address = f"Двойная{uuid.uuid4().hex[:6]} ул. 1"
    kids, _ = _site(district_id, address, "Детская площадка")
    sport, _ = _site(district_id, address, "Спортивная площадка")
    ambiguous = _write_csv(tmp_path / "a.csv", ["Адрес;№ люка", f"{address};1"])
    out = _run("--file", ambiguous, "--apply", capsys=capsys)
    assert "несколько площадок" in out
    assert _hatches(kids) == [] and _hatches(sport) == []

    typed = _write_csv(tmp_path / "b.csv", ["Адрес;Тип площадки;№ люка", f"{address};Спортивная;1"])
    _run("--file", typed, "--apply", capsys=capsys)
    assert _hatches(kids) == []
    assert [h[0] for h in _hatches(sport)] == ["1"]


def test_deactivate_missing_only_with_flag(tmp_path, capsys):
    district_id, _ = _district()
    street = f"Выключаемая{uuid.uuid4().hex[:6]}"
    site_id, _ = _site(district_id, f"{street} ул. 3")
    full = _write_csv(tmp_path / "full.csv", ["Адрес;№ люка", f"{street} ул. 3;1", f"{street} ул. 3;2"])
    _run("--file", full, "--apply", capsys=capsys)
    partial = _write_csv(tmp_path / "part.csv", ["Адрес;№ люка", f"{street} ул. 3;1"])
    _run("--file", partial, "--apply", capsys=capsys)
    assert [(h[0], h[4]) for h in _hatches(site_id)] == [("1", True), ("2", True)]
    # люк другого района, которого тоже нет в файле, выключаться не должен
    other_district, _ = _district()
    other_street = f"Чужая{uuid.uuid4().hex[:6]}"
    other_site, _ = _site(other_district, f"{other_street} ул. 1")
    _run("--file", _write_csv(tmp_path / "other.csv", ["Адрес;№ люка", f"{other_street} ул. 1;7"]),
         "--apply", capsys=capsys)

    _run("--file", partial, "--apply", "--deactivate-missing", capsys=capsys)
    assert [(h[0], h[4]) for h in _hatches(site_id)] == [("1", True), ("2", False)]
    assert [(h[0], h[4]) for h in _hatches(other_site)] == [("7", True)]
