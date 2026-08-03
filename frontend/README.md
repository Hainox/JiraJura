# Frontend — Журнал обхода площадок САО

PWA-клиент на React 19 + TypeScript + Vite. Общее описание проекта и запуск связки с backend — в [корневом README](../README.md).

## Команды

```bash
npm install
npm run dev       # dev-сервер, http://localhost:5173, проксирует /api/v1 на localhost:8000
npm run build      # проверка типов (tsc -b) + прод-сборка в dist/
npm run preview    # локальный просмотр прод-сборки
npm run lint        # oxlint
```

## Структура `src/`

- `pages/` — экраны: логин, регистрация по приглашению, карта площадок, карточка площадки, прохождение обхода, сводка, управление пользователями (только `admin`)
- `stores/` — состояние на Zustand: `auth` (JWT), `offline` (очередь действий без сети)
- `lib/api.ts` — HTTP-клиент (axios) с JWT-интерсептором; `baseURL` берётся из `VITE_API_URL` (build-time), по умолчанию — относительный `/api/v1` (фронтенд и бэкенд на одном origin через reverse proxy)
- `lib/roles.ts` — коды ролей (`inspector`/`reviewer`/`admin`) и их подписи на русском
- `types/` — общие TypeScript-типы, зеркалящие Pydantic-схемы backend

Маршрутизация с учётом ролей — `ProtectedRoute` в `App.tsx` принимает `roles?: Role[]` (например, `/admin/users` доступен только `admin`).

Алиас `@` указывает на `src/` (настроено в `vite.config.ts` и `tsconfig.app.json`).

PWA-манифест и офлайн-кэширование (Workbox) настроены в `vite.config.ts` через `vite-plugin-pwa`.
