# Backend — Журнал обхода площадок САО

FastAPI-приложение на Python 3.12 + PostgreSQL/PostGIS. Общее описание проекта — в [корневом README](../README.md).

## Запуск через Docker (рекомендуется)

```bash
docker compose up --build
```

Поднимает PostGIS на `localhost:5433` (накатывает `schema.sql` и `seed.sql`) и API на `http://localhost:8000` (`/docs` — Swagger UI).

## Запуск локально

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Нужен доступный PostgreSQL с расширением PostGIS; схема — `schema.sql`, тестовые данные — `seed.sql`.

## Конфигурация

Переменные окружения (`.env`, см. `app/config.py`):

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/sao_inspection` | строка подключения к БД |
| `SECRET_KEY` | `dev-secret-change-in-production` | ключ подписи JWT — обязательно сменить в продакшене |
| `ALGORITHM` | `HS256` | алгоритм подписи JWT |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | срок жизни токена (8 часов) |
| `UPLOAD_DIR` | `uploads` | директория для фото |
| `MAX_PHOTO_SIZE_MB` | `20` | лимит размера загружаемого фото (проверяется при загрузке) |
| `APP_ENV` | `development` | при `production` приложение откажется стартовать, если `SECRET_KEY` всё ещё дефолтный |
| `CORS_ORIGINS` | `http://localhost:5173` | список разрешённых origin через запятую |

## Миграции (Alembic)

```bash
alembic upgrade head        # применить все миграции к DATABASE_URL из .env
alembic revision -m "..."   # новая ревизия (пишется вручную, см. пример в alembic/versions/)
```

`schema.sql` — быстрый способ поднять чистую БД локально (накатывается автоматически в `docker-compose.yml` через `docker-entrypoint-initdb.d`). Для БД, уже созданной так, разово выполните `alembic stamp head`, чтобы Alembic считал её на последней ревизии, не переигрывая DDL. Дальше все изменения схемы — только через новые ревизии Alembic, `schema.sql` за ними не обновляется автоматически.

## Роли и права

`app/services/permissions.py`: `require_role(*roles)` — FastAPI-зависимость для эндпоинтов, доступных только определённым ролям; `check_own_or_role(user, owner_id, *roles)` — «своя запись или одна из ролей»; `in_district_scope(user, district_id)` — попадает ли район в зону видимости `reviewer`/`admin`. Роли: `inspector` / `reviewer` / `admin` — подробнее в [корневом README](../README.md#роли-и-регистрация).

## Структура

- `app/routers/` — эндпоинты: `auth` (login, приглашения, пользователи), `districts`,
  `courtyards`, `sites` (+ шаблоны чек-листов), `checklists`, `inspections`, `issues`,
  `reports`, `pdf_report`, `stats` (штабная статистика), `feedback`, `audit`, `system`
- `app/services/` — бизнес-логика: `auth.py` (JWT/пароли), `permissions.py`
  (роли/scoping), `issues.py` (SLA/критичность по типу нарушения), `statistics.py`,
  `safe_export.py` и `xlsx_style.py` (единый стиль Excel-отчётов, защита от
  формула-инъекций), `rate_limit.py`, `timezone.py`, `audit.py`
- `app/models.py` / `app/schemas.py` — ORM-модели (SQLAlchemy) и API-схемы (Pydantic)
- `alembic/` — миграции; `schema.sql` / `seed.sql` — DDL и тестовые данные для локальной БД
- `import_kml.py` — разовый скрипт импорта геометрии площадок из KML-файлов (детские/спортивные площадки) в PostGIS; пути к исходным KML в скрипте нужно указать под своё окружение
- Остальные `*.py` в корне `backend/` — разовые эксплуатационные скрипты (приглашения,
  диагностика логинов/фото, сверка площадок с перечнем, бэкфиллы, отчёты для деплоя) —
  см. docstring/`--help` каждого; полный список — в [корневом README](../README.md#структура-репозитория)
