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
| `MAX_PHOTO_SIZE_MB` | `20` | лимит размера загружаемого фото |

## Структура

- `app/routers/` — эндпоинты: `auth`, `districts`, `sites`, `inspections`, `issues`, `reports`
- `app/services/` — бизнес-логика
- `app/models.py` / `app/schemas.py` — ORM-модели (SQLAlchemy) и API-схемы (Pydantic)
- `schema.sql` / `seed.sql` — DDL и тестовые данные для локальной БД
- `import_kml.py` — разовый скрипт импорта геометрии площадок из KML-файлов (детские/спортивные площадки) в PostGIS; пути к исходным KML в скрипте нужно указать под своё окружение
