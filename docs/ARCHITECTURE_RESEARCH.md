# Глубокое исследование: Архитектура фронтенда для PWA «Журнал обхода площадок САО»

Дата: 2026-07-31 | 5 агентов swarm (1 завершён, 1 файл выгружен, 3 в процессе)

---

## 1. СТЕК: React + Vite + TypeScript

### Рекомендация
**React 19 + Vite 6 + TypeScript 5.7 + Tailwind CSS 4**

### Обоснование
| Критерий | React | Vue | Svelte |
|----------|-------|-----|--------|
| Мобильная производительность | ⭐⭐⭐⭐ (React 19 + concurrent) | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Размер бандла (PWA) | ~45 KB gzip (React 19) | ~33 KB gzip | ~8 KB gzip |
| Экосистема PWA | ⭐⭐⭐⭐⭐ (vite-plugin-pwa) | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| Компоненты карт | ⭐⭐⭐⭐⭐ (react-leaflet, @vis.gl/react-maplibre) | ⭐⭐⭐ | ⭐⭐ |
| Камера/геолокация | HTML5 API (одинаково для всех) | HTML5 API | HTML5 API |
| Offline-паттерны | TanStack Query + IndexedDB | VueUse + Pinia | Svelte stores |
| Кадры на рынке | Огромный пул разработчиков | Средний | Маленький |
| Поддержка PostGIS/GeoJSON | Отлично | Хорошо | Хорошо |

**Почему React:**
- Крупнейшая экосистема компонентов (особенно для карт — `react-leaflet`, `@vis.gl/react-maplibre`)
- `vite-plugin-pwa` — зрелая, проверенная интеграция с Workbox
- TanStack Query — лучшая библиотека для серверного состояния с офлайн-поддержкой
- React 19: Server Components не нужны для PWA, но concurrent rendering улучшает mobile UX

**Альтернатива (если нужна максимальная производительность):** Svelte 5 + SvelteKit. Но экосистема карт слабее.

---

## 2. КАРТЫ: Leaflet + OpenStreetMap

### Рекомендация
**Leaflet 1.9 + react-leaflet 5 + OpenStreetMap тайлы**

### Сравнение

| Критерий | Leaflet | MapLibre GL JS | 2ГИС API | Яндекс Карты |
|----------|---------|----------------|----------|-------------|
| Бесплатность | ✅ Полностью (OSM) | ✅ (свои тайлы) | ⚠️ 10K запросов/день | ⚠️ Коммерческая |
| GeoJSON-полигоны | ✅ Нативно | ✅ Нативно | ⚠️ Через API | ⚠️ Через API |
| Офлайн-тайлы | ✅ Через плагин | ✅ Через MBTiles | ❌ | ❌ |
| Мобильная произв. | ⭐⭐⭐⭐ (легковесный) | ⭐⭐⭐ (WebGL) | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| Кластеризация | ✅ (Leaflet.markercluster) | ✅ (supercluster) | ❌ | ✅ |
| Размер бандла | ~40 KB | ~200 KB | SDK внешний | SDK внешний |
| 3 814 полигонов | ✅ (canvas renderer) | ✅ | ❌ (лимит API) | ❌ (лимит API) |
| Свои тайлы | ✅ (свои XYZ) | ✅ (MBTiles/PMTiles) | ❌ | ❌ |

**Почему Leaflet:**
- Бесплатно, без лимитов — критично для муниципального проекта
- Нативная работа с GeoJSON (через API бэкенда)
- Легковесный (40 KB vs 200+ KB у MapLibre)
- Отличная поддержка мобильных — canvas-рендерер для тысяч полигонов
- Экосистема плагинов: кластеризация, офлайн-тайлы, heatmap, draw

**Офлайн-тайлы:** Для районов без связи — можно предзагрузить OSM-тайлы нужных zoom-уровней через leaflet-offline.

---

## 3. STATE MANAGEMENT: TanStack Query + Zustand

### Рекомендация (от агента turkey, подтверждаю)
**TanStack Query v5 — серверное состояние + кеширование**
**Zustand v5 — клиентское состояние (auth, offline queue, UI)**

### Архитектура

```
┌────────────────────────────────────────────────┐
│                  React App                     │
├────────────────────────────────────────────────┤
│  TanStack Query (серверное состояние)          │
│  ├─ useSites(districtId)    — площадки         │
│  ├─ useInspection(id)       — обход            │
│  ├─ useChecklistTemplates() — чек-листы        │
│  ├─ useIssues(filters)      — замечания        │
│  └─ useReports(period)      — отчёты           │
│     │                                          │
│     └─ persistQueryClient (IndexedDB)          │
│        — офлайн-кеш всех запросов              │
├────────────────────────────────────────────────┤
│  Zustand (клиентское состояние)                │
│  ├─ useAuthStore    — JWT токен, пользователь  │
│  ├─ useOfflineStore — очередь на синхронизацию │
│  └─ useUIStore      — активный экран, модалки  │
├────────────────────────────────────────────────┤
│  IndexedDB (Dexie.js)                          │
│  ├─ offlineQueue   — pending mutations         │
│  ├─ photoBlobs     — фото до синхронизации     │
│  └─ gpsTrack       — GPS-точки обхода          │
└────────────────────────────────────────────────┘
```

### Поток офлайн-синхронизации

```
1. Инспектор создаёт обход без сети
2. Данные сохраняются в IndexedDB (Dexie.js)
3. Фото сохраняются как Blob в IndexedDB
4. Мутация добавляется в offlineQueue
5. При восстановлении сети:
   a. Service Worker ловит событие 'sync'
   b. offlineQueue.process() отправляет накопленные мутации
   c. optimistic update сменяется реальным ответом сервера
6. После успешной синхронизации — запись удаляется из очереди
```

---

## 4. PWA / OFFLINE: vite-plugin-pwa + Workbox

### Стратегия

| Тип ресурса | Стратегия | Обоснование |
|------------|-----------|-------------|
| HTML (index.html) | NetworkFirst | Всегда свежая версия |
| JS/CSS бандлы | CacheFirst (precache) | Не меняются между деплоями |
| OSM тайлы | CacheFirst (30 дней) | Карта не меняется |
| API-ответы | NetworkFirst (5 мин) | Свежие данные приоритет |
| Фото (uploads) | NetworkOnly | Всегда на сервер |
| Шрифты/иконки | CacheFirst (precache) | Статический контент |

### Конфигурация vite-plugin-pwa

```ts
// vite.config.ts
import { VitePWA } from 'vite-plugin-pwa'

VitePWA({
  registerType: 'autoUpdate',
  workbox: {
    globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
    runtimeCaching: [
      {
        urlPattern: /^https:\/\/api\..*\/api\/v1\//,
        handler: 'NetworkFirst',
        options: { cacheName: 'api-cache', expiration: { maxAgeSeconds: 300 } }
      },
      {
        urlPattern: /^https:\/\/tile\.openstreetmap\.org\//,
        handler: 'CacheFirst',
        options: { cacheName: 'map-tiles', expiration: { maxAgeSeconds: 2592000 } }
      }
    ]
  },
  manifest: {
    name: 'Журнал обхода площадок САО',
    short_name: 'Обход САО',
    theme_color: '#2563EB',
    background_color: '#F9FAFB',
    display: 'standalone',
    orientation: 'portrait-primary',
    icons: [
      { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
      { src: '/icon-512.png', sizes: '512x512', type: 'image/png' }
    ]
  }
})
```

### Офлайн-хранилище (Dexie.js)

```ts
// db.ts
import Dexie from 'dexie'

const db = new Dexie('sao_inspection')
db.version(1).stores({
  offlineQueue: '++id, type, payload, createdAt',
  photoBlobs: '++id, inspectionId, itemId, blob, createdAt',
  gpsTrack: '++id, inspectionId, lat, lon, accuracy, timestamp',
  draftInspections: 'id, siteId, status, data'
})
```

---

## 5. UX-ПОТОК ОБХОДА

Полный wireframe: **`ux-wireframe-obhod-ploshadok.md`** (639 строк, создан агентом whale)

Краткая структура экранов:

```
Экран 1: Карта площадок
  ├─ Pin-ы с цветовой кодировкой (зелёный/жёлтый/красный/серый)
  ├─ Мини-карточка (bottom sheet) при тапе
  └─ Переключатель Список / Карта

Экран 2: Карточка площадки
  ├─ Фото, площадь, статус, история обходов
  └─ CTA «Начать обход»

Экран 3: Активный обход — категории чек-листа
  ├─ Прогресс-бар, таймер, GPS-статус
  ├─ Карточки категорий (покрытие/оборудование/МАФ/ограждение)
  └─ «Завершить обход» (активен после оценки всех пунктов)

Экран 4: Пункты категории
  ├─ Список пунктов с ОК/Не ОК
  ├─ Bottom sheet оценки (фото, комментарий, GPS)
  └─ «Создать замечание» (для «Не ОК»)

Экран 5: Создание замечания
  ├─ Тип проблемы, критичность, описание
  ├─ Фото (мин. 1), GPS, назначение, срок
  └─ Кнопка «Создать»

Экран 6: Завершение — сводка
  ├─ Результаты по категориям
  ├─ GPS-трек на мини-карте
  ├─ Подпись инспектора (canvas)
  └─ «Отправить обход»
```

---

## 6. ФИНАЛЬНАЯ СТРУКТУРА ПРОЕКТА

```
frontend/
├── public/
│   ├── icon-192.png
│   ├── icon-512.png
│   └── manifest.json
├── src/
│   ├── api/
│   │   ├── client.ts          — axios/fetch с JWT-интерсептором
│   │   ├── auth.ts            — login, me
│   │   ├── districts.ts       — список районов
│   │   ├── sites.ts           — площадки, чек-листы
│   │   ├── inspections.ts     — обходы (CRUD)
│   │   └── issues.ts          — замечания
│   ├── components/
│   │   ├── layout/
│   │   │   ├── BottomNav.tsx
│   │   │   ├── OfflineBanner.tsx
│   │   │   └── InspectionHeader.tsx
│   │   ├── map/
│   │   │   ├── SiteMap.tsx     — Leaflet карта
│   │   │   ├── SiteMarker.tsx  — pin площадки
│   │   │   └── MiniCard.tsx    — bottom sheet
│   │   ├── inspection/
│   │   │   ├── CategoryCard.tsx
│   │   │   ├── ChecklistItem.tsx
│   │   │   ├── ItemSheet.tsx   — оценка пункта
│   │   │   └── PhotoGrid.tsx
│   │   └── issue/
│   │       └── IssueForm.tsx
│   ├── hooks/
│   │   ├── useAuth.ts
│   │   ├── useGeolocation.ts
│   │   └── useOfflineSync.ts
│   ├── stores/
│   │   ├── authStore.ts       — Zustand
│   │   ├── offlineStore.ts    — Zustand
│   │   └── uiStore.ts         — Zustand
│   ├── db/
│   │   └── index.ts           — Dexie.js schema
│   ├── pages/
│   │   ├── MapPage.tsx
│   │   ├── SitePage.tsx
│   │   ├── InspectionPage.tsx
│   │   ├── CategoryPage.tsx
│   │   ├── IssuePage.tsx
│   │   └── SummaryPage.tsx
│   ├── App.tsx
│   └── main.tsx
├── index.html
├── package.json
├── tsconfig.json
├── tailwind.config.ts
└── vite.config.ts
```

---

## 7. ИТОГОВАЯ МАТРИЦА РЕШЕНИЙ

| Домен | Выбор | Альтернатива |
|-------|-------|-------------|
| Фреймворк | **React 19 + Vite 6** | Svelte 5 (если приоритет — бандл) |
| Язык | **TypeScript 5.7** | — |
| Стили | **Tailwind CSS 4** | — |
| Карты | **Leaflet + react-leaflet** | MapLibre GL JS |
| Тайлы | **OpenStreetMap** | Свои MBTiles для офлайна |
| State (server) | **TanStack Query v5** | SWR |
| State (client) | **Zustand v5** | Jotai |
| Offline DB | **Dexie.js (IndexedDB)** | OPFS (новее, но менее зрелая) |
| PWA | **vite-plugin-pwa + Workbox** | — |
| Маршрутизация | **React Router v7** | TanStack Router |
| Формы | **React Hook Form + Zod** | — |
| Иконки | **Lucide React** | — |

---

## 8. ПЛАН РЕАЛИЗАЦИИ (следующие шаги)

1. **Инициализация проекта** — `npm create vite@latest`, настройка Tailwind, PWA
2. **JWT-авторизация** — страница логина, хранение токена, интерсептор
3. **Карта площадок** — Leaflet + GeoJSON через API, кластеризация, лист/карта
4. **Карточка площадки** — детальная информация, история обходов
5. **Чек-лист обхода** — категории → пункты → оценка с фото
6. **Создание замечаний** — форма с фото, GPS, назначением
7. **Офлайн-режим** — Dexie.js, offlineQueue, фоновая синхронизация
8. **Сводка и подпись** — завершение обхода, canvas-подпись
9. **Отчёты** — дашборд для руководителей
10. **PWA-оптимизация** — splash screen, A2HS, push-уведомления
