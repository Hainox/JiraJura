@AGENTS.md

## Облачная песочница Claude Code
- Рабочая копия может откатиться на старый коммит между сообщениями, а `git fetch` в ней — вернуть устаревшие данные. Доверяй свежему клону: `rm -rf /tmp/jj_fresh && git clone --quiet https://github.com/Hainox/JiraJura.git /tmp/jj_fresh && git -C /tmp/jj_fresh log --oneline -10`; в него можно пушить, работай прямо в нём.
- Postgres может умереть между сообщениями (`Connection refused`): `pg_ctlcluster 16 main start && sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';"`. Если `backend/.venv` нет или он сломан: `cd backend && python3 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt -r requirements.txt`.
- Ручная проверка миграции на базе как в проде: создай `jirajura_migtest`, `CREATE EXTENSION postgis` и `"uuid-ossp"`, загрузи `backend/schema.sql`, `alembic stamp <ревизия до твоей>`, затем upgrade / `downgrade -1` / upgrade с `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/jirajura_migtest`.
- Исходящий HTTPS работает через прокси; порт 22 закрыт, SSH к серверу не повторяй.
