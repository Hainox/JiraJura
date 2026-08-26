# -*- coding: utf-8 -*-
"""Записать результат деплоя (успех/провал + хвост лога) в audit_log —
пишет deploy-watcher.sh (см. deploy/scripts/) после выполнения git pull/
build/up/alembic по маркеру от list_deploy_requests.py. Не человек
напрямую, но можно запускать и вручную.

Самодостаточный, как diagnose_logins.py — не импортирует app.models.
Лог читается из stdin, а не аргументом — чтобы не тащить через
shell-экранирование произвольные символы (кавычки, спецсимволы) в выводе
git/docker/alembic.

Запуск на сервере:
  cat deploy.log | docker compose -f docker-compose.prod.yml exec -T api \\
    python record_deploy_result.py --entity-id <uuid> --ok
  cat deploy.log | docker compose -f docker-compose.prod.yml exec -T api \\
    python record_deploy_result.py --entity-id <uuid> --fail
"""
import argparse
import asyncio
import json
import os
import sys
import uuid as _uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/sao_inspection")
MAX_LOG_CHARS = 4000


async def main(entity_id: str, ok: bool, log_tail: str):
    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    details = json.dumps(
        {"ok": ok, "log_tail": log_tail[-MAX_LOG_CHARS:]},
        ensure_ascii=False,
    )
    async with Session() as db:
        await db.execute(text(
            "INSERT INTO audit_log (id, user_id, action, entity_type, entity_id, details, created_at) "
            "VALUES (:id, NULL, 'deploy_completed', 'deployment', :entity_id, :details, :created_at)"
        ), {
            "id": str(_uuid.uuid4()),
            "entity_id": entity_id,
            "details": details,
            "created_at": datetime.now(timezone.utc),
        })
        await db.commit()
    await engine.dispose()
    print(f"Записан результат деплоя {entity_id}: ok={ok}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--entity-id", required=True)
    p.add_argument("--ok", dest="ok", action="store_true")
    p.add_argument("--fail", dest="ok", action="store_false")
    p.set_defaults(ok=True)
    args = p.parse_args()
    stdin_log = sys.stdin.read()
    asyncio.run(main(args.entity_id, args.ok, stdin_log))
