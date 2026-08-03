# Электронный журнал обхода площадок САО

PWA-приложение для учёта обходов детских и спортивных площадок Северного административного округа (САО) г. Москвы: инспекторы фиксируют состояние оборудования по чек-листу, создают замечания с фото и GPS-привязкой, руководители видят сводные отчёты на карте.

## Стек

**Backend** — FastAPI (Python 3.12) · PostgreSQL + PostGIS · SQLAlchemy 2.0 (async) · JWT-авторизация · Alembic

**Frontend** — React 19 + TypeScript · Vite · Tailwind CSS 4 · React Router 7 · TanStack Query · Zustand · React Leaflet (карта) · vite-plugin-pwa (офлайн-режим)

## Структура репозитория

```
.
├── backend/            FastAPI-приложение
│   ├── app/
│   │   ├── routers/    auth, districts, sites, inspections, issues, reports
│   │   ├── services/   бизнес-логика (auth и т.д.)
│   │   ├── models.py   SQLAlchemy ORM-модели
│   │   ├── schemas.py  Pydantic-схемы
│   │   └── main.py     точка входа FastAPI
│   ├── schema.sql       DDL: районы, площадки, оборудование, обходы, замечания...
│   ├── seed.sql         тестовый пользователь для локальной разработки
│   ├── import_kml.py    импорт геометрии площадок из KML в PostGIS
│   └── docker-compose.yml
├── frontend/            PWA-клиент (Vite + React)
│   └── src/
│       ├── pages/       Login, Map, SiteDetail, Inspection, Summary
│       ├── stores/      Zustand: auth, офлайн-очередь
│       └── lib/api.ts   HTTP-клиент (axios + JWT-интерсептор)
└── docs/
    ├── ARCHITECTURE_RESEARCH.md                              обоснование выбора стека
    └── Техническое_задание_Электронный_журнал_обхода.docx    ТЗ
```

## Быстрый старт

### Backend + база данных (Docker)

```bash
cd backend
docker compose up --build
```

Поднимет PostgreSQL/PostGIS на `localhost:5433` (схема и seed-данные накатываются автоматически) и API на `http://localhost:8000` (Swagger-документация — `/docs`).

Тестовый аккаунт из `seed.sql`: `admin` / `admin123` — только для локальной разработки, перед продакшеном обязательно завести реальных пользователей и сменить `SECRET_KEY`.

### Backend без Docker

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# нужен PostgreSQL с расширением PostGIS, см. schema.sql / seed.sql
uvicorn app.main:app --reload
```

Конфигурация — через переменные окружения (`.env` в `backend/`, см. `app/config.py`): `DATABASE_URL`, `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `UPLOAD_DIR`, `MAX_PHOTO_SIZE_MB`.

### Frontend

```bash
cd frontend
npm install
npm run dev       # dev-сервер на :5173, проксирует /api/v1 на localhost:8000
npm run build      # прод-сборка
npm run lint       # oxlint
```

## API

Основные группы эндпоинтов (`/api/v1/...`): `auth` (login/me), `districts`, `sites` (+ чек-лист шаблонов), `inspections` (+ фото), `issues`, `reports` (weekly/monthly). Полная спецификация — Swagger UI по `/docs` после запуска backend.

## Статус проекта

Реализовано: авторизация по JWT, карта площадок, детальная карточка площадки, прохождение обхода по чек-листу с фото и созданием замечаний, сводка обхода, недельные/месячные отчёты, базовая офлайн-очередь действий.

В планах (см. `docs/ARCHITECTURE_RESEARCH.md`): перевод офлайн-очереди на IndexedDB (Dexie.js) для надёжного хранения фото до синхронизации, кластеризация меток на карте, push-уведомления, офлайн-кэш тайлов карты.
