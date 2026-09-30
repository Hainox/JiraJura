import { useState, useEffect, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { MapContainer, TileLayer, Marker, Popup, useMap, AttributionControl } from 'react-leaflet'
import MarkerClusterGroup from 'react-leaflet-cluster'
import L from 'leaflet'
import { sitesApi, districtsApi, reportsApi, inspectionsApi } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { useMapViewStore } from '@/stores/mapView'
import { guardDemoAction } from '@/stores/demoMode'
import type { SiteOut, DistrictOut, InspectionOut } from '@/types'
import { List, Map as MapIcon, LogOut, ChevronRight, Settings2, Download, ClipboardCheck, AlertCircle, UserCircle, BarChart3, History, CheckCheck, Filter, HelpCircle } from 'lucide-react'
import { notify as toast } from '@/lib/toast'
import InspectionReviewList from '@/components/InspectionReviewList'
import MoreMenu, { type MoreMenuItem } from '@/components/MoreMenu'
import {
  CHILD_TYPE, SPORT_TYPE, VISITED_STATUSES, COVERAGE_LEGEND,
  countVisitedToday, markerColor, markerLabel,
} from '@/lib/mapMarkers'
import 'leaflet/dist/leaflet.css'
import 'leaflet.markercluster/dist/MarkerCluster.css'
import 'leaflet.markercluster/dist/MarkerCluster.Default.css'

const moscowToday = () => {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/Moscow', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date())
  const value = (type: string) => parts.find((part) => part.type === type)?.value
  return `${value('year')}-${value('month')}-${value('day')}`
}

const siteIcon = (siteType: string | undefined, status?: string | null) => L.divIcon({
  className: 'custom-icon',
  html: `<div style="background:${markerColor(status)};color:white;width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:bold;box-shadow:0 2px 6px rgba(0,0,0,.3);border:2px solid white">${markerLabel(siteType, status)}</div>`,
  iconSize: [26, 26], iconAnchor: [13, 13],
})

function CoverageLegend({ visited, total }: { visited?: number; total: number }) {
  return (
    <div role="group" aria-label="Легенда карты" className="bg-white border-b px-3 py-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-gray-600 shrink-0">
      {COVERAGE_LEGEND.map(({ state, label, color }) => (
        <span key={state} className="flex items-center gap-1">
          <span aria-hidden="true" className="w-3 h-3 rounded-full inline-block shrink-0" style={{ background: color }} />
          {label}
        </span>
      ))}
      <span className="text-gray-400">Д — детская, С — спортивная</span>
      {visited !== undefined && (
        <span className="ml-auto font-semibold text-gray-700">Сегодня обойдено: {visited}/{total}</span>
      )}
    </div>
  )
}

function FitBounds({ data }: { data: SiteOut[] | undefined }) {
  const map = useMap()
  useEffect(() => {
    if (data?.length) {
      const points = data.filter((s) => s.lat != null && s.lon != null)
      if (points.length > 0) {
        const lats = points.map((s) => s.lat!)
        const lons = points.map((s) => s.lon!)
        const bounds = L.latLngBounds(lats.map((lat, i) => [lat, lons[i]] as L.LatLngTuple))
        map.fitBounds(bounds, { padding: [30, 30] })
      } else {
        map.setView([55.829, 37.532], 12)
      }
    }
  }, [data, map])
  return null
}

export default function MapPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const logoutStore = useAuthStore((s) => s.logout)
  // Фильтры/вкладка/скролл — в сторе (useMapViewStore), а не в useState:
  // раньше при возврате на карту из площадки/списка обходов (кнопка
  // "назад" или переход по ссылке) страница монтировалась заново и все
  // фильтры/выбранная вкладка слетали на дефолт. Стор живёт вне дерева
  // компонентов и переживает размонтирование страницы.
  const viewMode = useMapViewStore((s) => s.viewMode)
  const setViewMode = useMapViewStore((s) => s.setViewMode)
  const districtFilter = useMapViewStore((s) => s.districtFilter)
  const setDistrictFilter = useMapViewStore((s) => s.setDistrictFilter)
  const typeFilter = useMapViewStore((s) => s.typeFilter)
  const setTypeFilter = useMapViewStore((s) => s.setTypeFilter)
  const reviewStatusFilter = useMapViewStore((s) => s.reviewStatusFilter)
  const setReviewStatusFilter = useMapViewStore((s) => s.setReviewStatusFilter)
  const myInspOnly = useMapViewStore((s) => s.myInspOnly)
  const setMyInspOnly = useMapViewStore((s) => s.setMyInspOnly)
  const selectedMyAssignedOnly = useMapViewStore((s) => s.myAssignedOnly)
  // Персональное назначение — дополнительный режим только для инспектора;
  // базовый список всегда содержит весь район пользователя.
  const myAssignedOnly = user?.role === 'inspector' && selectedMyAssignedOnly
  const setMyAssignedOnly = useMapViewStore((s) => s.setMyAssignedOnly)
  // Не подписываемся на listScrollTop через селектор — иначе каждый пиксель
  // скролла ре-рендерил бы всю страницу (setter вызывается на каждый onScroll).
  // Читаем/пишем через getState() напрямую, см. эффект восстановления ниже.
  const setListScrollTop = useMapViewStore((s) => s.setListScrollTop)
  const listRef = useRef<HTMLDivElement>(null)
  // Панели-раскрывашки — не "контекст", просто текущее состояние UI,
  // можно оставить локальными
  const [showFilters, setShowFilters] = useState(false)
  const todayMsk = moscowToday()

  const isAdmin = user?.role === 'admin'
  const isReviewerLike = user?.role === 'reviewer' || isAdmin
  // Приёмка обходов у админа переехала в отдельный /admin/reviews — админ
  // больше не должен ощущать себя "проверяющим" на этой странице, вкладка
  // "Проверка" здесь остаётся только для роли reviewer.
  const showReviewTab = user?.role === 'reviewer'

  const { data: districts } = useQuery<DistrictOut[]>({
    queryKey: ['districts'],
    queryFn: districtsApi.list,
  })

  const effectiveDistrictFilter = isAdmin ? districtFilter : (user?.district_id ?? districtFilter)

  const {
    data: sitesData,
    isLoading: sitesLoading,
    isError: sitesError,
    refetch: refetchSites,
  } = useQuery({
    queryKey: ['sites', effectiveDistrictFilter, typeFilter, myAssignedOnly],
    queryFn: () => sitesApi.list({
      // Для scoped-пользователей район всегда определяет сервер по свежему
      // current_user. Не отправляем cached district_id из localStorage:
      // после переназначения он может быть старым и раньше давал пустое
      // пересечение двух районных фильтров до повторного входа.
      district_id: isAdmin ? districtFilter : undefined,
      type: typeFilter, page_size: 5000,
      assigned_to_me: user?.role === 'inspector' && myAssignedOnly || undefined,
    }),
    // Админ без выбранного района не загружает все площадки — слишком долго
    enabled: !isAdmin || !!districtFilter,
  })

  // Лёгкий запрос только за количеством (page_size=1 — та же count-выборка
  // без загрузки геометрий), чтобы бейдж "Все районы (N)" показывал реальное
  // число площадок, а не 0 из-за того что полный список ещё не загружен
  const { data: allSitesCountData } = useQuery({
    queryKey: ['sites-count-all', typeFilter],
    queryFn: () => sitesApi.list({ type: typeFilter, page_size: 1 }),
    enabled: isAdmin,
  })
  const allSitesTotal = allSitesCountData?.total ?? 0

  // Обходы для режима проверки — раньше грузились одним запросом на
  // page_size=1000 (максимум бэкенда, le=1000 в list_inspections) и
  // фильтровались по вкладке уже на клиенте. При 200 старые обходы молча
  // выпадали из очереди на проверку (реальная жалоба из поля — "не вижу
  // обходы"); подняли до 1000 — тот же тупик наступил снова, когда обходов
  // по округу стало больше 1000. Теперь вкладка сама определяет статус
  // (см. reviewStatusParams) — сервер фильтрует и считает total по
  // выбранной вкладке, а не по всей истории района, и "Показать ещё"
  // догружает следующую страницу, а не молча теряет хвост.
  const REVIEW_PAGE_SIZE = 1000
  const reviewStatusParams: { status?: string; exclude_status?: string } =
    reviewStatusFilter === 'all' ? {}
    : reviewStatusFilter === 'pending' ? { exclude_status: 'completed' }
    : { status: reviewStatusFilter }

  const {
    data: inspectionsPages,
    fetchNextPage: fetchNextInspectionsPage,
    hasNextPage: hasMoreInspections,
    isFetchingNextPage: isLoadingMoreInspections,
  } = useInfiniteQuery({
    queryKey: ['inspections-review', effectiveDistrictFilter, reviewStatusFilter],
    queryFn: ({ pageParam }) => inspectionsApi.list({
      district_id: effectiveDistrictFilter, page_size: REVIEW_PAGE_SIZE, page: pageParam, ...reviewStatusParams,
    }),
    initialPageParam: 1,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((sum, p) => sum + p.items.length, 0)
      return loaded < lastPage.total ? allPages.length + 1 : undefined
    },
    enabled: viewMode === 'review' && showReviewTab,
  })

  // Отдельный лёгкий запрос (page_size=1, без фильтра по вкладке — тот же
  // приём, что и allSitesCountData выше) только за общим числом обходов на
  // проверку в районе, для бейджа на кнопке "Проверка" — он не должен
  // прыгать в зависимости от того, какая вкладка сейчас выбрана.
  const { data: reviewQueueCountData } = useQuery({
    queryKey: ['inspections-review-count', effectiveDistrictFilter],
    queryFn: () => inspectionsApi.list({ district_id: effectiveDistrictFilter, page_size: 1 }),
    enabled: showReviewTab,
  })
  const reviewQueueTotal = reviewQueueCountData?.total ?? 0

  const sites = sitesData?.items ?? []
  const totalCount = sitesData?.total ?? sites.length
  const allInspections = useMemo(
    () => inspectionsPages?.pages.flatMap((p) => p.items) ?? [],
    [inspectionsPages],
  )
  const inspectionsTotal = inspectionsPages?.pages[0]?.total ?? 0

  // Восстанавливаем позицию скролла списка площадок при возврате на вкладку
  // "Список" (напр. открыл площадку из середины списка, нажал "назад" —
  // раньше список всегда прыгал обратно наверх).
  useEffect(() => {
    if (viewMode === 'list' && listRef.current) {
      listRef.current.scrollTop = useMapViewStore.getState().listScrollTop
    }
  }, [viewMode, sites.length])

  const handleListScroll = (e: React.UIEvent<HTMLDivElement>) => {
    setListScrollTop(e.currentTarget.scrollTop)
  }

  // Проверяющий принимает "зелёный" (без замечаний) обход одним нажатием,
  // не открывая его — статус не меняется (уже completed), но фиксируется
  // reviewed_by/reviewed_at
  const acceptInspectionMutation = useMutation({
    mutationFn: (inspectionId: string) => inspectionsApi.update(inspectionId, { status: 'completed' }),
    onSuccess: () => {
      toast.success('Обход принят')
      queryClient.invalidateQueries({ queryKey: ['inspections-review'] })
    },
    onError: () => toast.error('Не удалось принять обход'),
  })

  const bulkAcceptMutation = useMutation({
    mutationFn: (ids: string[]) => inspectionsApi.bulkAccept(ids),
    onSuccess: ({ accepted, skipped }) => {
      toast.success(skipped > 0 ? `Принято обходов: ${accepted} (пропущено: ${skipped})` : `Принято обходов: ${accepted}`)
      queryClient.invalidateQueries({ queryKey: ['inspections-review'] })
    },
    onError: () => toast.error('Не удалось принять обходы'),
  })

  // Обходы для раскраски меток берём только за текущий московский день.
  // Исторический обход остаётся в журнале площадки, но не должен создавать
  // ложную зелёную галочку и скрывать площадку из «Только необойдённые».
  // Инспектор видит коллег по своему району, чтобы не дублировать работу.
  const { data: districtInspectionsData } = useQuery<{ total: number; items: InspectionOut[] }>({
    queryKey: ['district-inspections-map', effectiveDistrictFilter, todayMsk],
    queryFn: () => inspectionsApi.list({
      page_size: 1000, district_id: effectiveDistrictFilter,
      date_from: todayMsk, date_to: todayMsk,
      all_in_district: user?.role === 'inspector' || undefined,
    }),
    enabled: user?.role === 'inspector' || isReviewerLike,
  })
  const myInspections = districtInspectionsData?.items ?? []

  // Карта: site_id → сегодняшний обход (статус + кто/когда).
  // Зависимость от districtInspectionsData?.items, а не от производного
  // `myInspections ?? []` — тот новый массив на каждый рендер, useMemo
  // пересчитывался бы впустую (см. тот же паттерн в MyInspectionsPage).
  const siteStatusMap = useMemo(() => {
    const map: Record<string, { status: string; inspectorName: string; date: string }> = {}
    for (const insp of districtInspectionsData?.items ?? []) {
      if (!map[insp.site_id] || insp.created_at > map[insp.site_id].date) {
        map[insp.site_id] = { status: insp.status, inspectorName: insp.inspector.full_name, date: insp.created_at }
      }
    }
    return map
  }, [districtInspectionsData?.items])

  // Фильтр по вкладке теперь применяется на сервере (reviewStatusParams
  // выше) — allInspections уже содержит только нужный вкладке статус.
  const visitedToday = districtInspectionsData
    ? countVisitedToday(sites.map((s) => s.id), siteStatusMap)
    : undefined

  const bulkAcceptableIds = allInspections
    .filter((i) => !i.reviewed_by && i.status === 'completed' && (i.issues_count ?? 0) === 0)
    .map((i) => i.id)

  const center: L.LatLngExpression = [55.829, 37.532]

  const moreMenuItems: MoreMenuItem[] = [
    { label: 'Профиль', icon: <UserCircle className="w-5 h-5 text-gray-500" />, prefetch: '/profile', onSelect: () => navigate('/profile') },
    ...(user?.role !== 'inspector' ? [{
      label: 'Выгрузка в Excel',
      icon: <Download className="w-5 h-5 text-gray-500" />,
      onSelect: () => toast.promise(reportsApi.exportXlsx({ district_id: districtFilter }), {
        loading: 'Готовлю файл...', success: 'Файл скачан', error: 'Ошибка выгрузки',
      }),
    }] : []),
    { label: 'Выйти', icon: <LogOut className="w-5 h-5" />, danger: true, onSelect: () => { logoutStore(); navigate('/login') } },
  ]

  return (
    <div className="h-full flex flex-col">
      {/* Шапка: подписи у кнопок видны всегда — title-подсказки на телефоне
          не показываются, и иконки без слов пользователи не узнавали.
          Редкие действия убраны в «Ещё», чтобы строка помещалась в 360 px. */}
      <div className="bg-primary-800 text-white shrink-0">
        <div className="px-4 pt-2 flex items-center justify-between gap-2">
          <div className="min-w-0">
            <h1 className="text-lg font-bold leading-tight">Обход площадок</h1>
            <p className="text-blue-200 text-xs truncate">
              {user?.full_name}
              {user?.role === 'reviewer' && <span className="ml-1 text-amber-300">(проверяющий)</span>}
            </p>
          </div>
          <MoreMenu items={moreMenuItems} />
        </div>
        <nav aria-label="Разделы" className="px-2 pt-1 pb-1.5 flex gap-1">
          {user?.role === 'inspector' && (
            <HeaderNavButton icon={<History className="w-5 h-5" />} label="История" title="История обходов" prefetch="/my-inspections" onClick={() => navigate('/my-inspections')} />
          )}
          {/* Админ пользуется своими /admin/dashboard и /admin/issues через
              «Управление» (Админ-панель) — не должен попадать на reviewer-
              роуты /dashboard и /issues (roles={['reviewer']} в App.tsx). */}
          {user?.role === 'reviewer' && (
            <>
              <HeaderNavButton icon={<BarChart3 className="w-5 h-5" />} label="Статистика" title="Статистика (дашборд)" prefetch="/dashboard" onClick={() => navigate('/dashboard')} />
              <HeaderNavButton icon={<AlertCircle className="w-5 h-5" />} label="Замечания" title="Замечания района" prefetch="/issues" onClick={() => navigate('/issues')} />
            </>
          )}
          {user?.role === 'admin' && (
            <HeaderNavButton icon={<Settings2 className="w-5 h-5" />} label="Управление" title="Управление (админ-панель)" prefetch="/admin" onClick={() => navigate('/admin')} />
          )}
          <HeaderNavButton
            icon={<Filter className="w-5 h-5" />}
            label="Фильтры"
            title="Фильтры и район"
            active={showFilters}
            expanded={showFilters}
            onClick={() => setShowFilters((v) => !v)}
          />
          <HeaderNavButton icon={<HelpCircle className="w-5 h-5" />} label="Помощь" title="Помощь и ответы на вопросы" prefetch="/help" onClick={() => navigate('/help')} />
        </nav>
      </div>

      {/* Фильтры */}
      {showFilters && (
        <div className="bg-white border-b px-4 py-2 shrink-0 space-y-2">
          <div className="flex gap-2">
            {isAdmin ? (
              <select className="input-field text-sm flex-1" value={districtFilter ?? ''} onChange={(e) => setDistrictFilter(e.target.value || undefined)}>
                <option value="">Все районы ({allSitesTotal} площадок)</option>
                {districts?.map((d) => (<option key={d.id} value={d.id}>{d.name}</option>))}
              </select>
            ) : (
              <div className="input-field text-sm flex-1 flex items-center text-gray-700">
                {user?.district_id
                  ? (districts?.find((d) => d.id === user.district_id)?.name ?? 'Район не назначен')
                  : 'Весь округ'}
              </div>
            )}
            <select className="input-field text-sm flex-1" value={typeFilter ?? ''} onChange={(e) => setTypeFilter(e.target.value || undefined)}>
              <option value="">Все типы</option>
              <option value={CHILD_TYPE}>Детские</option>
              <option value={SPORT_TYPE}>Спортивные</option>
            </select>
          </div>
          {user?.role === 'inspector' && (
            <div className="flex items-center gap-2">
              <button
                onClick={() => setMyAssignedOnly(!myAssignedOnly)}
                className={`text-xs px-3 py-1 rounded-full font-medium transition-colors ${
                  myAssignedOnly ? 'bg-primary-700 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                Мои назначенные площадки
              </button>
            </div>
          )}
          {user?.role === 'inspector' && myInspections.length > 0 && (
            <div className="flex items-center gap-2">
              <button
                onClick={() => setMyInspOnly(!myInspOnly)}
                className={`text-xs px-3 py-1 rounded-full font-medium transition-colors ${
                  myInspOnly ? 'bg-primary-700 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                Только необойдённые
              </button>
            </div>
          )}
        </div>
      )}

      {/* View toggle */}
      <div className="flex bg-white border-b px-4 py-2 gap-2 shrink-0">
        <button
          onClick={() => setViewMode('map')}
          className={`flex-1 py-1.5 text-sm font-medium rounded-lg flex items-center justify-center gap-1.5 transition-colors ${
            viewMode === 'map' ? 'bg-primary-700 text-white' : 'bg-gray-100 text-gray-600'
          }`}
        >
          <MapIcon className="w-4 h-4" /> Карта
        </button>
        <button
          onClick={() => setViewMode('list')}
          className={`flex-1 py-1.5 text-sm font-medium rounded-lg flex items-center justify-center gap-1.5 transition-colors ${
            viewMode === 'list' ? 'bg-primary-700 text-white' : 'bg-gray-100 text-gray-600'
          }`}
        >
          <List className="w-4 h-4" /> Список
        </button>
        {showReviewTab && (
          <button
            onClick={() => setViewMode('review')}
            className={`flex-1 py-1.5 text-sm font-medium rounded-lg flex items-center justify-center gap-1.5 transition-colors ${
              viewMode === 'review' ? 'bg-amber-600 text-white' : 'bg-amber-50 text-amber-700 hover:bg-amber-100'
            }`}
          >
            <ClipboardCheck className="w-4 h-4" /> Проверка
            {reviewQueueTotal > 0 && (
              <span className="text-xs ml-0.5">({reviewQueueTotal})</span>
            )}
          </button>
        )}
      </div>

      {/* Фильтр статусов для режима проверки */}
      {viewMode === 'review' && showReviewTab && (
        <div className="bg-white border-b px-4 py-2 shrink-0 space-y-2">
          <div className="flex gap-2 overflow-x-auto">
            {[
              { key: 'all', label: `Все (${inspectionsTotal})` },
              { key: 'pending', label: 'На проверку' },
              { key: 'completed', label: 'Принятые' },
              { key: 'issues_found', label: 'С нарушениями' },
              { key: 'critical', label: 'Критические' },
            ].map((f) => (
              <button
                key={f.key}
                onClick={() => setReviewStatusFilter(f.key)}
                className={`shrink-0 px-3 py-1 text-xs rounded-full font-medium transition-colors ${
                  reviewStatusFilter === f.key
                    ? 'bg-primary-700 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
          {reviewStatusFilter === 'completed' && bulkAcceptableIds.length > 0 && (
            <button
              onClick={() => {
                if (confirm(`Принять сразу ${bulkAcceptableIds.length} обходов без замечаний?`)) {
                  guardDemoAction(() => bulkAcceptMutation.mutate(bulkAcceptableIds))
                }
              }}
              disabled={bulkAcceptMutation.isPending}
              className="w-full btn-primary text-sm py-2 flex items-center justify-center gap-2 disabled:opacity-50"
            >
              <CheckCheck className="w-4 h-4" />
              {bulkAcceptMutation.isPending ? 'Принимаем...' : `Принять все (${bulkAcceptableIds.length})`}
            </button>
          )}
        </div>
      )}

      {/* Content */}
      <div className="flex-1 min-h-0">
        {/* Инспектор без назначенного района — бэкенд молча отдаёт 0 площадок
            (см. sites.py), внешне неотличимо от "в районе правда нет
            площадок". Реальная причина жалоб вида "задания не отображаются" —
            объясняем прямо, а не оставляем пустую карту без единого слова. */}
        {user?.role === 'inspector' && !user?.district_id ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center max-w-sm px-4">
              <div className="inline-flex items-center justify-center w-16 h-16 bg-amber-100 rounded-2xl mb-4">
                <AlertCircle className="w-8 h-8 text-amber-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-700 mb-2">Район не назначен</h3>
              <p className="text-sm text-gray-500">
                Вашему аккаунту не назначен район, поэтому площадки не отображаются. Обратитесь к администратору, чтобы он указал ваш район.
              </p>
            </div>
          </div>
        ) : viewMode !== 'review' && sitesLoading ? (
          <div className="h-full flex items-center justify-center text-sm text-gray-400">
            Загружаем площадки...
          </div>
        ) : viewMode !== 'review' && sitesError ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center max-w-sm px-4">
              <div className="inline-flex items-center justify-center w-16 h-16 bg-red-100 rounded-2xl mb-4">
                <AlertCircle className="w-8 h-8 text-red-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-700 mb-2">Не удалось загрузить площадки</h3>
              <p className="text-sm text-gray-500">
                Это ошибка связи или сервера, а не отсутствие площадок в районе.
              </p>
              <button onClick={() => refetchSites()} className="btn-primary mt-4">
                Повторить загрузку
              </button>
            </div>
          </div>
        ) : /* "Мои площадки" при нуле персональных назначений выглядит
            неотличимо от "в районе вообще нет площадок" — реальный случай
            из поля (инспектор с 0 assigned_inspector_id решил, что все
            площадки пропали). Назначение площадок пока используется не
            повсеместно, так что это не редкий край, а частый первый опыт
            с этим фильтром. */
        user?.role === 'inspector' && myAssignedOnly && !sitesLoading && sites.length === 0 && viewMode !== 'review' ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center max-w-sm px-4">
              <div className="inline-flex items-center justify-center w-16 h-16 bg-amber-100 rounded-2xl mb-4">
                <AlertCircle className="w-8 h-8 text-amber-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-700 mb-2">Нет персонально назначенных площадок</h3>
              <p className="text-sm text-gray-500">
                Включён дополнительный фильтр «Мои назначенные площадки», а за вами пока не закреплено ни одной конкретной площадки. Отключите его, чтобы увидеть все площадки района.
              </p>
              <button
                onClick={() => setMyAssignedOnly(false)}
                className="btn-primary mt-4"
              >
                Показать все площадки района
              </button>
            </div>
          </div>
        ) : viewMode !== 'review' && sites.length === 0 && !!typeFilter ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center max-w-sm px-4">
              <div className="inline-flex items-center justify-center w-16 h-16 bg-amber-100 rounded-2xl mb-4">
                <AlertCircle className="w-8 h-8 text-amber-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-700 mb-2">Фильтр скрыл все площадки</h3>
              <p className="text-sm text-gray-500">
                В выбранном районе нет площадок этого типа. Сбросьте фильтр, чтобы увидеть остальные.
              </p>
              <button onClick={() => setTypeFilter(undefined)} className="btn-primary mt-4">
                Показать все типы
              </button>
            </div>
          </div>
        ) : /* Админ без выбранного района — показываем плейсхолдер (кроме вкладки
            "Проверка": список обходов там не зависит от выбора района) */
        isAdmin && !districtFilter && viewMode !== 'review' ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center max-w-sm px-4">
              <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-100 rounded-2xl mb-4">
                <MapIcon className="w-8 h-8 text-blue-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-700 mb-2">Выберите район</h3>
              <p className="text-sm text-gray-500">
                Нажмите «Фильтры» в шапке и выберите район для отображения площадок.
              </p>
              <button
                onClick={() => setShowFilters(true)}
                className="btn-primary mt-4"
              >
                Открыть фильтры
              </button>
            </div>
          </div>
        ) : viewMode === 'review' && showReviewTab ? (
          <InspectionReviewList
            inspections={allInspections}
            emptyLabel={reviewStatusFilter !== 'all' ? 'Нет обходов с этим статусом' : 'Нет обходов для проверки'}
            onAccept={(id) => guardDemoAction(() => acceptInspectionMutation.mutate(id))}
            acceptPending={acceptInspectionMutation.isPending}
            hasMore={hasMoreInspections}
            loadingMore={isLoadingMoreInspections}
            onLoadMore={() => fetchNextInspectionsPage()}
          />
        ) : viewMode === 'map' ? (
          <div className="h-full flex flex-col">
            <CoverageLegend visited={visitedToday} total={totalCount} />
            <div className="flex-1 min-h-0">
              <MapContainer center={center} zoom={12} className="h-full w-full" attributionControl={false}>
                <AttributionControl prefix={false} />
                <TileLayer
                  attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                  maxZoom={19}
                />
                <FitBounds data={sites} />
                {/* Кластеризация — при 3800+ площадках плоский список меток
                    делал карту нечитаемой и тяжёлой при отдалении. */}
                <MarkerClusterGroup
                  chunkedLoading
                  maxClusterRadius={60}
                  spiderfyOnMaxZoom
                  // На большом зуме площадки уже различимы по отдельности —
                  // кластеризация там только мешает выбору конкретной метки.
                  disableClusteringAtZoom={17}
                  // Не рисуем полупрозрачный полигон зоны охвата кластера при
                  // наведении — на карте с 3800+ площадками это визуальный шум.
                  showCoverageOnHover={false}
                >
                  {sites.filter((s) => !myInspOnly || !siteStatusMap[s.id] || !VISITED_STATUSES.has(siteStatusMap[s.id].status)).map((s) => {
                    const coverage = (user?.role === 'inspector' || isReviewerLike) ? siteStatusMap[s.id] : undefined
                    const icon = siteIcon(s.type, coverage?.status)
                    return <Marker key={s.id} position={[s.lat ?? 55.829, s.lon ?? 37.532]} icon={icon}>
                      <Popup>
                        <div className="min-w-[180px]">
                          <div className="font-semibold text-sm">{s.courtyard?.name ?? 'Площадка'}</div>
                          <div className="text-xs text-gray-500 mt-0.5">{s.district?.name}</div>
                          <div className="text-xs text-gray-400 mt-0.5">
                            {s.type === CHILD_TYPE ? 'Детская' : 'Спортивная'} • {s.area_m2} м²
                          </div>
                          {isReviewerLike && (
                            <div className="text-xs text-gray-400 mt-0.5">
                              {s.assigned_inspector ? `Назначена: ${s.assigned_inspector.full_name}` : 'Не назначена'}
                            </div>
                          )}
                          {user?.role === 'inspector' && coverage && (
                            <div className="text-xs text-gray-400 mt-0.5">
                              Сегодня обошёл: {coverage.inspectorName}
                            </div>
                          )}
                          <button onClick={() => navigate(`/sites/${s.id}`)} data-prefetch={`/sites/${s.id}`} className="mt-2 text-xs btn-primary py-1 px-3 w-full flex items-center justify-center gap-1">
                            Открыть <ChevronRight className="w-3 h-3" />
                          </button>
                        </div>
                      </Popup>
                    </Marker>
                  })}
                </MarkerClusterGroup>
              </MapContainer>
            </div>
          </div>
        ) : (
          <div className="h-full flex flex-col">
            <CoverageLegend visited={visitedToday} total={totalCount} />
            <div ref={listRef} onScroll={handleListScroll} className="flex-1 min-h-0 overflow-y-auto p-3 space-y-2">
              {sites.map((s) => (
                <button key={s.id} onClick={() => navigate(`/sites/${s.id}`)} data-prefetch={`/sites/${s.id}`} className="card w-full text-left hover:border-primary-300 transition-colors">
                  <div className="flex items-start gap-3">
                    {/* Цвет — статус сегодняшнего обхода, как на карте и в
                        легенде; тип площадки — буквой. */}
                    <div className="w-10 h-10 rounded-xl flex items-center justify-center text-white text-lg shrink-0" style={{ background: markerColor(siteStatusMap[s.id]?.status) }}>
                      {markerLabel(s.type, siteStatusMap[s.id]?.status)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold text-sm truncate">{s.courtyard?.name ?? 'Площадка'}</div>
                      <div className="text-xs text-gray-500 mt-0.5">{s.district?.name}</div>
                      <div className="text-xs text-gray-400 mt-0.5">{s.type}{' • '}{s.area_m2} м²</div>
                      {isReviewerLike && (
                        <div className="text-xs text-gray-400 mt-0.5">
                          {s.assigned_inspector ? `Назначена: ${s.assigned_inspector.full_name}` : 'Не назначена'}
                        </div>
                      )}
                      {user?.role === 'inspector' && siteStatusMap[s.id] && (
                        <div className="text-xs text-gray-400 mt-0.5">
                          Сегодня обошёл: {siteStatusMap[s.id].inspectorName}
                        </div>
                      )}
                    </div>
                    <ChevronRight className="w-4 h-4 text-gray-300 shrink-0 mt-3" />
                  </div>
                </button>
              ))}
              {sites.length === 0 && (<div className="text-center text-gray-400 py-12">Нет площадок</div>)}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function HeaderNavButton({ icon, label, title, onClick, prefetch, active, expanded }: {
  icon: React.ReactNode
  label: string
  title: string
  onClick: () => void
  prefetch?: string
  active?: boolean
  expanded?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-prefetch={prefetch}
      title={title}
      aria-expanded={expanded}
      className={`flex-1 min-w-0 min-h-11 px-1 py-1 rounded-lg flex flex-col items-center justify-center gap-0.5 text-[11px] font-medium leading-tight transition-colors sm:flex-none sm:flex-row sm:gap-1.5 sm:px-3 sm:text-sm ${
        active ? 'bg-primary-700' : 'hover:bg-primary-700'
      }`}
    >
      {icon}
      <span className="truncate max-w-full">{label}</span>
    </button>
  )
}
