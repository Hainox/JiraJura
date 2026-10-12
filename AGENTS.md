# AGENTS.md

## Unwritten
- Publishing: agents never push to `main` (the owner may); branch + PR, squash-merge after green CI. Agents cannot reach the production server (outbound SSH is blocked in agent sandboxes), so server work ships as ready commands or scripts for the owner. A deploy is `git pull`, build, `up -d` per `deploy/README.md`; the `api` container applies migrations on start, and the in-app «Деплой» button queues a request that `deploy/scripts/deploy-watcher.sh` (host cron) executes.
- Gotchas: Alembic must keep exactly one head: run `git fetch` + `alembic heads` right before `alembic revision`, not only at session start, because the other agent may merge a migration meanwhile. Each pytest run recreates the `jirajura_test` DB via `alembic upgrade head` + `seed.sql` (`backend/tests/conftest.py`), so it needs local Postgres + PostGIS and every migration runs in CI. openpyxl `BarChart`/`LineChart` default both axes to `axPos="l"`; set `chart.x_axis.axPos = "b"` or Excel draws no category labels.
- Checks: `cd backend && pytest -q`; `cd frontend && npm run lint && npm run build && npm test`; for a migration, `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` again. CI also validates proxy/nginx configs (`bash deploy/tests/test_*_proxy_config.sh`, `nginx -t` in Docker).
- Conventions: UI text, commits, and PRs are in Russian. Branches carry the author prefix (`claude/...`, `codex/...`, `<login>/...`); never reuse another agent's prefix. One PR, one task; each agent keeps its own PR's CI green. Test data is generated in the test, never real names, phones, or logins.
- Why: Alembic revisions are hand-written raw SQL (`op.execute`), not autogenerate, and use `IF NOT EXISTS` because fresh installs get `backend/schema.sql` and `upgrade head` then replays revisions over it; keep `schema.sql` in sync. All time metrics are Moscow time via `app.services.timezone.msk_day_bounds_utc`; timezone bugs were fixed here repeatedly, so do not write new TZ logic. The coordination rules below exist because in Aug 2026 both agents wrote the same `add_issue_categories` migration and PR #104 had to be closed over multiple heads.

## Agent coordination
- Claude Code and Codex CLI work independently with no live channel; they coordinate only through git history, PRs, review comments, and `docs/coordination/`.
- Before any task: `git fetch origin main`, `git log --oneline -20 origin/main`, `gh pr list`, and check `docs/coordination/STATUS.md` for the area being `in_progress` elsewhere.
- `STATUS.md` is the board (`planned → in_progress → review → approved → deployed`): whoever starts a task adds or updates its row, whoever closes the PR moves it on; update its «Handoff» section before ending a session with unfinished work.
- `docs/coordination/DECISIONS.md` is an append-only log of decisions another agent would otherwise reconstruct from diffs. To disagree with another agent's decision, record the alternative there or comment on the open PR; escalate architecturally significant divergence to the owner instead of rewriting.
- Review means opening the changed files, checking PR claims with a repo-wide grep, and running migrations up and down on a test DB.

## Pointers
- **Writing** or reviewing code: apply `CODING_STANDARDS.md`; project config and linters win where they disagree.
- **Security**-sensitive change (auth, permissions, untrusted input, secrets): read `docs/agents/security.md` first.
- **Committing** or opening a PR: follow `docs/agents/git.md`.
- **Risky** change (spans modules, migrates data, alters a public API): propose a phased plan and get approval before editing.
- **Done** means you ran the project's own check commands and they are green, or you named the ones you could not run.
