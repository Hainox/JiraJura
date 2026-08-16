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
│   │   ├── routers/    auth, districts, sites, courtyards, inspections, issues,
│   │   │               checklists, reports, pdf_report, audit, system
│   │   ├── services/   бизнес-логика (auth, permissions, audit, timezone и т.д.)
│   │   ├── models.py   SQLAlchemy ORM-модели
│   │   ├── schemas.py  Pydantic-схемы
│   │   └── main.py     точка входа FastAPI
│   ├── schema.sql       DDL: районы, площадки, оборудование, обходы, замечания...
│   ├── seed.sql         тестовый пользователь для локальной разработки
│   ├── import_kml.py    импорт геометрии площадок из KML в PostGIS
│   ├── bulk_invite.py, reissue_invites.py, split_invites_by_district.py,
│   │   roster_district_status.py, verify_invite_links.py, diagnose_logins.py,
│   │   fix_passwords.py, reset_shared_passwords.py, production_status_report.py,
│   │   generate_summary_report.py, apply_titul.py   разовые эксплуатационные
│   │                                                  скрипты, см. деплой-README
│   └── docker-compose.yml
├── frontend/            PWA-клиент (Vite + React)
│   └── src/
│       ├── pages/       Login, Register, ChangePassword, Map, SiteDetail, Inspection,
│       │               Summary, Profile, MyInspections, Dashboard, Issues, IssueFix,
│       │               Audit, AdminPanel, AdminUsers, AdminSites, AdminChecklists,
│       │               AdminReviews, AdminSystem
│       ├── stores/      Zustand: auth, демо-режим, вид карты
│       └── lib/api.ts   HTTP-клиент (axios + JWT-интерсептор)
├── deploy/              Продакшн-деплой (docker-compose.prod.yml, nginx, certbot, бэкапы) — см. deploy/README.md
└── docs/
    ├── ARCHITECTURE_RESEARCH.md                              обоснование выбора стека
    ├── user-onboarding.md, video-instruction-*.md            инструкции для сотрудников
    └── Техническое_задание_Электронный_журнал_обхода.docx    ТЗ
```

## Быстрый старт

### Backend + база данных (Docker)

```bash
cd backend
docker compose up --build
```

Поднимет PostgreSQL/PostGIS на `localhost:5433` (схема и seed-данные накатываются автоматически из `schema.sql`/`seed.sql`) и API на `http://localhost:8000` (Swagger-документация — `/docs`).

Тестовый аккаунт из `seed.sql`: `admin` / `admin123` (роль `admin`) — только для локальной разработки, перед продакшеном обязательно сменить `SECRET_KEY` и завести реальных пользователей через приглашения (см. «Роли и регистрация» ниже).

Схема БД эволюционирует через Alembic (`backend/alembic/`) — `schema.sql` остаётся быстрым способом поднять БД с нуля локально, `alembic upgrade head` — способ обновить уже существующую (в т.ч. продакшн) базу. Для БД, уже созданной через `schema.sql`, разово выполните `alembic stamp head`, дальше — только миграции.

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

Основные группы эндпоинтов (`/api/v1/...`): `auth` (login/me, приглашения, управление пользователями), `districts`, `sites` (+ чек-лист шаблонов), `inspections` (+ фото), `issues`, `reports` (weekly/monthly). Полная спецификация — Swagger UI по `/docs` после запуска backend.

## Роли и регистрация

Три роли (`backend/app/models.py`, `USER_ROLE_ENUM`):

| Роль | Видит | Может |
|---|---|---|
| **Инспектор** (`inspector`) | только свои обходы/замечания | создавать обходы, заполнять чек-лист, грузить фото, создавать замечания |
| **Проверяющий** (`reviewer`) | свою зону: район, если задан `district_id`, иначе весь округ | то же, что инспектор, плюс менять статус замечаний, смотреть отчёты по своей зоне |
| **Админ** (`admin`) | всё | всё вышеперечисленное без ограничений + управление пользователями |

Открытой самостоятельной регистрации нет — админ создаёт приглашение («Пользователи» → «Пригласить» в UI, либо `POST /api/v1/auth/invites`) с логином/ФИО/ролью/районом, получает одноразовую ссылку `/register/<token>` (действует 72 часа) и передаёт её человеку; тот сам задаёт себе пароль. Первого админа на новом окружении приходится завести вручную (см. `deploy/README.md`, шаг 3) — дальше все аккаунты заводятся через приглашения.

## Деплой в продакшн

См. **[`deploy/README.md`](deploy/README.md)** — production `docker-compose.prod.yml`, nginx + Let's Encrypt (certbot), бэкапы. Рассчитано на разворачивание рядом с другими Docker-сервисами на том же сервере без пересечения по портам/сетям/файлам.

## Статус проекта

Развёрнуто и работает в проде (`journal.yuvibot2.xyz:8443`): авторизация по JWT (со сменой пароля/сбросом админом), приглашения и роли (инспектор/проверяющий/админ) со scoping по району, карта и список площадок, детальная карточка площадки, прохождение обхода по чек-листу с обязательными фото (общее + по отмеченным пунктам с requires_photo), полная линия замечаний «выявлено → в работе → устранено (с фото до/после) → принято/на доработку», приёмка обходов (в т.ч. массовая), сводные Excel/PDF-отчёты, аудит-лог действий, раздел «Разработчик» для админа, CRUD площадок/дворов/чек-листов через админ-панель, Alembic-миграции, CI (backend pytest + frontend lint/test/build), автотесты (Login/Register), production-деплой (Docker Compose + nginx/certbot + автобэкапы).

В планах (см. `docs/ARCHITECTURE_RESEARCH.md`): перевод офлайн-очереди на IndexedDB (Dexie.js) для надёжного хранения фото до синхронизации, push-уведомления. Кластеризация меток на карте (`react-leaflet-cluster`, отключается на крупном зуме) и офлайн-кэш тайлов OSM (Workbox `CacheFirst`) уже реализованы.
