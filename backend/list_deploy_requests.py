# -*- coding: utf-8 -*-
"""Список ещё не обработанных маркеров "запрошен деплой" (action=
'deploy_requested', entity_type='deployment' в audit_log — их пишет
POST /api/v1/system/deploy/request, кнопка «Деплой» в разделе
«Разработчик»). Читает deploy-watcher.sh (см. deploy/scripts/), не
человек напрямую — но можно запускать и вручную для проверки.

Самодостаточный, как diagnose_logins.py — не импортирует app.models.
Только читает, ничего не меняет.

Печатает по одной строке на маркер: "<entity_id>\t<created_at ISO>",
отсортировано по возрастанию времени. Пусто — новых маркеров нет.

Запуск на сервере:
  docker compose -f docker-compose.prod.yml exec -T api python list_deploy_requests.py --since 2026-08-25T00:00:00+00:00
"""
import argparse
import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/sao_inspection")


async def main(since: str):
    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        rows = (await db.execute(text(
            "SELECT entity_id, created_at FROM audit_log "
            "WHERE action = 'deploy_requested' AND created_at > :since "
            "ORDER BY created_at ASC"
        ), {"since": since})).fetchall()
        for entity_id, created_at in rows:
            print(f"{entity_id}\t{created_at.isoformat()}")
    await engine.dispose()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--since", required=True, help="ISO-timestamp с таймзоной — только маркеры позже этого времени")
    args = p.parse_args()
    asyncio.run(main(args.since))
