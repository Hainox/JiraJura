@AGENTS.md

## Claude Code cloud sandbox
- The working copy can roll back to an old commit between messages, and `git fetch` there may return stale data. Trust a fresh clone: `git clone --quiet https://github.com/Hainox/JiraJura.git /tmp/jj_fresh && git -C /tmp/jj_fresh log --oneline -10`; it is pushable, so you can work in it directly.
- Postgres may die between messages (`Connection refused`): `pg_ctlcluster 16 main start && sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';"`. A missing or broken `backend/.venv`: `python3 -m venv .venv && pip install -q -r requirements-dev.txt -r requirements.txt`.
- Manual migration check against a prod-like DB: create `jirajura_migtest`, `CREATE EXTENSION postgis` and `"uuid-ossp"`, load `backend/schema.sql`, `alembic stamp <revision before yours>`, then upgrade / `downgrade -1` / upgrade with `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/jirajura_migtest`.
- Outbound HTTPS works through a proxy; port 22 is blocked, so do not retry SSH to the server.
