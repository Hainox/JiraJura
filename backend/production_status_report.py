# -*- coding: utf-8 -*-
"""Сводка по статусу проекта — читает БД, ничего не меняет.

Часть 1: регистрация по районам — сколько уже зарегистрировано vs сколько
ещё ждёт (по инвайтам без used_at), с именами тех, кто не зарегистрирован,
районы отсортированы по проценту регистрации (худшие сверху).

Часть 2: сводка по работе — обходы/нарушения по районам, самый
активный/пассивный район.

Запуск на сервере:
  docker compose -f docker-compose.prod.yml exec api python production_status_report.py
"""
import asyncio
import os
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/sao_inspection")


async def main():
    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        # ═══ Часть 1: регистрация по районам ═══════════════════════
        districts = (await db.execute(text(
            "SELECT id, name FROM districts ORDER BY name"
        ))).fetchall()

        pending_rows = (await db.execute(text(
            "SELECT district_id, full_name, login, role "
            "FROM user_invites WHERE used_at IS NULL ORDER BY full_name, created_at DESC"
        ))).fetchall()

        # дедуп по ФИО (как в reissue_invites.py) — не размножаем дубли-логины на одного человека
        seen_names_global = set()
        pending_by_district = defaultdict(list)
        pending_admins = []
        pending_okrug_reviewers = []
        for r in pending_rows:
            if r.full_name in seen_names_global:
                continue
            seen_names_global.add(r.full_name)
            if r.role == "admin":
                pending_admins.append(r)
            elif r.district_id is None:
                pending_okrug_reviewers.append(r)
            else:
                pending_by_district[r.district_id].append(r)

        district_stats = []
        for d in districts:
            registered = (await db.execute(text(
                "SELECT COUNT(*) FROM users WHERE district_id = :did AND is_active"
            ), {"did": d.id})).scalar()
            pending = pending_by_district.get(d.id, [])
            total = registered + len(pending)
            pct = (registered / total * 100) if total else 100.0
            district_stats.append((d.name, registered, len(pending), total, pct, pending))

        district_stats.sort(key=lambda x: x[4])

        print("═" * 70)
        print("ЧАСТЬ 1: РЕГИСТРАЦИЯ ПО РАЙОНАМ (худшие сверху)")
        print("═" * 70)
        total_reg = sum(x[1] for x in district_stats)
        total_all = sum(x[3] for x in district_stats)
        overall_pct = (total_reg / total_all * 100) if total_all else 100.0
        print(f"\nПо округу в целом: {total_reg}/{total_all} зарегистрировано ({overall_pct:.0f}%)\n")

        for name, registered, pending_count, total, pct, pending in district_stats:
            marker = "⚠" if pct < 50 else (" " if pct >= 90 else "·")
            print(f"{marker} {name:30s} {registered:3d}/{total:3d}  ({pct:5.1f}%)")
            if pending:
                for r in pending:
                    print(f"      не зарегистрирован(а): {r.full_name}  [{r.login}]")

        if pending_okrug_reviewers:
            print(f"\nПроверяющие без района (весь округ) — не зарегистрировано: {len(pending_okrug_reviewers)}")
            for r in pending_okrug_reviewers:
                print(f"      {r.full_name}  [{r.login}]")

        if pending_admins:
            print(f"\nАдмины — не зарегистрировано: {len(pending_admins)}")
            for r in pending_admins:
                print(f"      {r.full_name}  [{r.login}]")

        # ═══ Часть 2: сводка по работе ══════════════════════════════
        print("\n" + "═" * 70)
        print("ЧАСТЬ 2: СВОДКА ПО РАБОТЕ")
        print("═" * 70)

        work_stats = []
        for d in districts:
            site_ids = (await db.execute(text(
                "SELECT s.id FROM sites s JOIN courtyards c ON c.id = s.courtyard_id "
                "WHERE c.district_id = :did AND s.is_active"
            ), {"did": d.id})).fetchall()
            site_ids = [r.id for r in site_ids]
            if not site_ids:
                work_stats.append((d.name, 0, 0, 0, 0, 0, 0, 0, 0))
                continue

            insp_total, insp_done = (await db.execute(text(
                "SELECT COUNT(*), COUNT(*) FILTER (WHERE status = 'completed') "
                "FROM inspections WHERE site_id = ANY(:sids)"
            ), {"sids": site_ids})).fetchone()

            iss_total, iss_open, iss_fixed, iss_revision, iss_closed = (await db.execute(text(
                "SELECT COUNT(*), "
                "COUNT(*) FILTER (WHERE status = 'open'), "
                "COUNT(*) FILTER (WHERE status = 'fixed'), "
                "COUNT(*) FILTER (WHERE status = 'revision_needed'), "
                "COUNT(*) FILTER (WHERE status = 'closed') "
                "FROM issues WHERE site_id = ANY(:sids)"
            ), {"sids": site_ids})).fetchone()

            work_stats.append((d.name, len(site_ids), insp_total, insp_done, iss_total, iss_open, iss_fixed, iss_revision, iss_closed))

        total_sites = sum(x[1] for x in work_stats)
        total_insp = sum(x[2] for x in work_stats)
        total_insp_done = sum(x[3] for x in work_stats)
        total_iss = sum(x[4] for x in work_stats)
        total_iss_open = sum(x[5] for x in work_stats)
        total_iss_fixed = sum(x[6] for x in work_stats)
        total_iss_revision = sum(x[7] for x in work_stats)
        total_iss_closed = sum(x[8] for x in work_stats)

        print(f"\nПо округу: площадок {total_sites}, обходов {total_insp} (завершено {total_insp_done}), "
              f"нарушений {total_iss} (открыто {total_iss_open}, исправлено {total_iss_fixed}, "
              f"на доработке {total_iss_revision}, принято {total_iss_closed})\n")

        by_inspections = sorted(work_stats, key=lambda x: x[3], reverse=True)
        most_active = [x for x in by_inspections if x[3] > 0][:3]
        most_passive = [x for x in by_inspections if x[3] == 0 or x == by_inspections[-1]]
        least_active = sorted(work_stats, key=lambda x: x[3])[:3]

        print("Самые активные районы (по завершённым обходам):")
        for name, sites, insp_t, insp_d, iss_t, *_ in most_active:
            print(f"   {name:30s} обходов завершено: {insp_d:3d}  нарушений: {iss_t:3d}")

        print("\nСамые пассивные районы (по завершённым обходам):")
        for name, sites, insp_t, insp_d, iss_t, *_ in least_active:
            print(f"   {name:30s} обходов завершено: {insp_d:3d}  из {sites} площадок")

        print("\nПодробно по районам:")
        print(f"{'Район':30s} {'Площ.':>6s} {'Обходов':>8s} {'Заверш.':>8s} {'Наруш.':>7s} {'Открыто':>8s} {'Исправл.':>9s} {'Доработ.':>9s} {'Принято':>8s}")
        for name, sites, insp_t, insp_d, iss_t, iss_o, iss_f, iss_r, iss_c in sorted(work_stats, key=lambda x: x[0]):
            print(f"{name:30s} {sites:6d} {insp_t:8d} {insp_d:8d} {iss_t:7d} {iss_o:8d} {iss_f:9d} {iss_r:9d} {iss_c:8d}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
