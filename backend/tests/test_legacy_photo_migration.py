"""Forward migration keeps legacy checklist evidence visible as issue evidence."""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg2
import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
SYNC_DB_URL = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")


def _exec(sql: str, params=None):
    with psycopg2.connect(SYNC_DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or {})


def _one(sql: str, params=None):
    with psycopg2.connect(SYNC_DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or {})
            return cursor.fetchone()


@pytest.mark.asyncio
async def test_migration_relinks_issue_photos_without_deleting_legacy_links(client):
    del client  # Initial fixture has created the isolated test database.
    env = os.environ.copy()
    subprocess.run([sys.executable, "-m", "alembic", "downgrade", "c0d1e2f3a4b5"], cwd=BACKEND_DIR, env=env, check=True)

    district_id, courtyard_id, site_id, inspection_id, answer_id, issue_id, issue_photo_id, general_photo_id = [str(uuid.uuid4()) for _ in range(8)]
    user_id = _one("SELECT id FROM users ORDER BY id LIMIT 1")[0]
    item_id = _one("SELECT id FROM checklist_items ORDER BY sort_order LIMIT 1")[0]
    category_id = _one("SELECT id FROM issue_categories WHERE is_active=true ORDER BY sort_order LIMIT 1")[0]
    _exec(
        "INSERT INTO districts(id,name,code) VALUES (%(district)s,'Legacy migration','legacy_migration');"
        "INSERT INTO courtyards(id,district_id,name) VALUES (%(courtyard)s,%(district)s,'Legacy courtyard');"
        "INSERT INTO sites(id,courtyard_id,type,area_m2,geometry,is_active) VALUES "
        "(%(site)s,%(courtyard)s,'Детская площадка',100,ST_GeomFromText("
        "'POLYGON((37 55,37.01 55,37.01 55.01,37 55.01,37 55))',4326),true);"
        "INSERT INTO inspections(id,site_id,inspector_id,type,status) VALUES (%(inspection)s,%(site)s,%(user)s,'regular','issues_found');"
        "INSERT INTO checklist_answers(id,inspection_id,checklist_item_id,result) VALUES (%(answer)s,%(inspection)s,%(item)s,'defect');"
        "INSERT INTO issues(id,inspection_id,site_id,checklist_answer_id,category_id,title,status,created_by) VALUES "
        "(%(issue)s,%(inspection)s,%(site)s,%(answer)s,%(category)s,'Legacy defect','open',%(user)s);"
        "INSERT INTO photos(id,target_type,inspection_id,checklist_answer_id,storage_path) VALUES "
        "(%(issue_photo)s,'checklist_answer',%(inspection)s,%(answer)s,'inspections/defect.jpg'),"
        "(%(general_photo)s,'checklist_answer',%(inspection)s,NULL,'inspections/general.jpg')",
        {"district": district_id, "courtyard": courtyard_id, "inspection": inspection_id, "answer": answer_id, "issue": issue_id,
         "issue_photo": issue_photo_id, "general_photo": general_photo_id,
         "site": site_id, "user": user_id, "item": item_id, "category": category_id},
    )

    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND_DIR, env=env, check=True)

    assert _one("SELECT target_type, issue_id, checklist_answer_id FROM photos WHERE id=%s", (issue_photo_id,)) == (
        "issue", issue_id, answer_id,
    )
    assert _one("SELECT target_type, issue_id, checklist_answer_id FROM photos WHERE id=%s", (general_photo_id,)) == (
        "inspection", None, None,
    )
