"""Скрипты, через которые deploy-watcher.sh (кнопка «Деплой») общается с БД:
list_deploy_requests.py читает новые запросы деплоя, record_deploy_result.py
пишет результат. Время последнего обработанного запроса watcher хранит в
state-файле текстом и передаёт обратно через --since — этот круг и проверяем.
"""
import argparse
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest

import list_deploy_requests
import record_deploy_result

SYNC_DB_URL = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")


def _exec(sql, params=None):
    with psycopg2.connect(SYNC_DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or ())
            return cursor.fetchall() if cursor.description else None


def _request(created_at: datetime) -> str:
    entity_id = str(uuid.uuid4())
    _exec(
        "INSERT INTO audit_log (action, entity_type, entity_id, details, created_at) "
        "VALUES ('deploy_requested', 'deployment', %s, '{}', %s)",
        (entity_id, created_at),
    )
    return entity_id


def test_lists_only_requests_after_state_file_time(capsys):
    base = datetime(2031, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=uuid.uuid4().int % 100000)
    old = _request(base)
    new = _request(base + timedelta(minutes=5))

    # Так --since приходит из state-файла: строкой, как её записал прошлый запуск.
    since = list_deploy_requests.parse_since((base + timedelta(minutes=1)).isoformat())
    asyncio.run(list_deploy_requests.main(since))

    lines = [line.split("\t") for line in capsys.readouterr().out.splitlines()]
    ids = [entity_id for entity_id, _ in lines]
    assert new in ids and old not in ids
    # Время из вывода уходит в state-файл и возвращается следующим --since.
    created_at = dict(lines)[new]
    assert list_deploy_requests.parse_since(created_at) == base + timedelta(minutes=5)


def test_since_requires_timezone():
    with pytest.raises(argparse.ArgumentTypeError):
        list_deploy_requests.parse_since("2026-09-30T21:14:00")
    with pytest.raises(argparse.ArgumentTypeError):
        list_deploy_requests.parse_since("вчера")
    assert list_deploy_requests.parse_since("2026-09-30T21:14:00Z").tzinfo is not None


def test_records_result_for_request():
    entity_id = _request(datetime.now(timezone.utc))
    asyncio.run(record_deploy_result.main(entity_id, True, "git pull … OK"))
    rows = _exec(
        "SELECT details FROM audit_log WHERE action = 'deploy_completed' AND entity_id = %s",
        (entity_id,),
    )
    assert len(rows) == 1 and '"ok": true' in rows[0][0]
