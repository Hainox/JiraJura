# CLAUDE.md — заметки для Claude Code на этом проекте

Общий протокол координации с другими агентами (Codex CLI и др.) — в
[`AGENTS.md`](./AGENTS.md), он обязателен и для меня тоже: чек-лист перед
началом задачи, правила веток/PR, ревью, журнал решений в
`docs/coordination/`. Этот файл — только специфичные для Claude Code
заметки, накопленные за время работы над проектом.

## Известная проблема песочницы: устаревший локальный git

В облачных сессиях случается, что `/home/user/JiraJura` откатывается к
старому коммиту между сообщениями (сброс контейнера), а `git fetch` в этом
же каталоге после этого иногда отдаёт устаревшие данные (не отражает
реальный `origin/main`). Надёжный способ проверить, что происходит на
самом деле:

```bash
rm -rf /tmp/jj_fresh && git clone --quiet https://github.com/Hainox/JiraJura.git /tmp/jj_fresh
cd /tmp/jj_fresh && git log --oneline -10
```

Если это расходится с тем, что показывает `git log` в рабочем каталоге —
доверять свежему клону, не рабочему каталогу. Для собственно правок можно
работать прямо в свежем клоне (он pushable теми же credentials).

## Локальный прогон тестов

Postgres в песочнице иногда падает между сообщениями — если `psql`
отвечает `Connection refused`, поднять заново:

```bash
pg_ctlcluster 16 main start
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';"
```

Дальше — обычный `cd backend && source .venv/bin/activate && python3 -m pytest -q`
(если `.venv` нет или сломан после сброса — `python3 -m venv .venv && pip install -q -r requirements-dev.txt -r requirements.txt`).
Frontend: `cd frontend && npm run lint && npm run build && npm test -- --run`.

Тестовая БД `jirajura_test` пересоздаётся автоматически (`tests/conftest.py`,
через `alembic upgrade head` + `seed.sql`) при каждом запуске pytest — не
нужно готовить её вручную.

## Проверка миграции руками (когда нужна уверенность, что накатится на проде)

```bash
psql -c "CREATE DATABASE jirajura_migtest"
psql -d jirajura_migtest -c "CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";"
psql -d jirajura_migtest -f backend/schema.sql
cd backend
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/jirajura_migtest alembic stamp <ревизия-до-новой>
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/jirajura_migtest alembic upgrade head
```
Проверить upgrade, downgrade -1, повторный upgrade (идемпотентность).

## Сеть из песочницы

- Исходящий HTTPS работает через прокси (обычные `curl`/`fetch`).
- Порт 22 (SSH) наружу заблокирован — на сервер приложения зайти нельзя
  напрямую; для серверных операций готовить скрипт и отдавать владельцу
  продукта на запуск, не пытаться повторно проверять доступность SSH.

## Стилевые соглашения (сверх того, что уже есть в README)

- openpyxl: у `BarChart`/`LineChart` по умолчанию `axPos="l"` на ОБЕИХ
  осях — для оси категорий обязательно ставить `chart.x_axis.axPos = "b"`
  явно, иначе Excel не рисует подписи категорий вообще (нашли на реальном
  скриншоте, не в тестах — openpyxl это не валидирует).
- Комментарии в коде — только там, где объясняется НЕПРОЗРАЧНАЯ причина
  (баг, который так чинили, инвариант, который не виден из кода) — не
  пересказ того, что и так видно из имён.
- Коммиты и PR — в том же стиле, что и вся история проекта: по-русски,
  без префиксов conventional-commits, объясняют «почему», а не «что».

## Рабочий процесс, устоявшийся в этом проекте

Небольшие PR на одну задачу, ветка `claude/...`, обязательные тесты перед
PR, squash-merge после зелёного CI. Для серверного деплоя — только готовые
команды/скрипты владельцу продукта, самостоятельно на сервер не заходить
(см. выше про SSH).
