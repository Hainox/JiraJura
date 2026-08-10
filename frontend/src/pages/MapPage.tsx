import { useState, useEffect, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { MapContainer, TileLayer, Marker, Popup, useMap, AttributionControl } from 'react-leaflet'
import MarkerClusterGroup from 'react-leaflet-cluster'
import L from 'leaflet'
import { sitesApi, districtsApi, reportsApi, inspectionsApi } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { useMapViewStore } from '@/stores/mapView'
import { guardDemoAction } from '@/stores/demoMode'
import type { SiteOut, DistrictOut, InspectionOut } from '@/types'
import { List, Map as MapIcon, LogOut, ChevronRight, Users, Download, ClipboardCheck, AlertCircle, UserCircle, BarChart3, History } from 'lucide-react'
import { notify as toast } from '@/lib/toast'
import InspectionReviewList from '@/components/InspectionReviewList'
import 'leaflet/dist/leaflet.css'
import 'leaflet.markercluster/dist/MarkerCluster.css'
import 'leaflet.markercluster/dist/MarkerCluster.Default.css'

const CHILD_TYPE = 'Детская площадка'
const SPORT_TYPE = 'Спортивная площадка'

const childIcon = (status?: string | null) => {
  const base = status === 'completed' ? '#16a34a' : status === 'in_progress' ? '#ca8a04' : status === 'issues_found' || status === 'critical' ? '#dc2626' : '#2563eb'
  const letter = status === 'completed' ? '✓' : 'Д'
  return L.divIcon({
    className: 'custom-icon',
    html: `<div style="background:${base};color:white;width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:bold;box-shadow:0 2px 6px rgba(0,0,0,.3);border:2px solid white">${letter}</div>`,
    iconSize: [26, 26], iconAnchor: [13, 13],
  })
}
const sportIcon = (status?: string | null) => {
  const base = status === 'completed' ? '#16a34a' : status === 'in_progress' ? '#ca8a04' : status === 'issues_found' || status === 'critical' ? '#dc2626' : '#16a34a'
  const letter = status === 'completed' ? '✓' : 'С'
  return L.divIcon({
    className: 'custom-icon',
    html: `<div style="background:${base};color:white;width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:bold;box-shadow:0 2px 6px rgba(0,0,0,.3);border:2px solid white">${letter}</div>`,
    iconSize: [26, 26], iconAnchor: [13, 13],
  })
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
  const myAssignedOnly = useMapViewStore((s) => s.myAssignedOnly)
  const setMyAssignedOnly = useMapViewStore((s) => s.setMyAssignedOnly)
  // Не подписываемся на listScrollTop через селектор — иначе каждый пиксель
  // скролла ре-рендерил бы всю страницу (setter вызывается на каждый onScroll).
  // Читаем/пишем через getState() напрямую, см. эффект восстановления ниже.
  const setListScrollTop = useMapViewStore((s) => s.setListScrollTop)
  const listRef = useRef<HTMLDivElement>(null)
  // Панели-раскрывашки — не "контекст", просто текущее состояние UI,
  // можно оставить локальными
  const [showFilters, setShowFilters] = useState(false)
  const [showLegend, setShowLegend] = useState(false)

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

  const { data: sitesData } = useQuery({
    queryKey: ['sites', effectiveDistrictFilter, typeFilter, myAssignedOnly],
    queryFn: () => sitesApi.list({
      district_id: effectiveDistrictFilter, type: typeFilter, page_size: 5000,
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

  // Загрузка обходов для режима проверки
  const { data: inspectionsData } = useQuery<{ total: number; items: InspectionOut[] }>({
    queryKey: ['inspections-review', effectiveDistrictFilter],
    queryFn: () => inspectionsApi.list({ district_id: effectiveDistrictFilter, page_size: 200 }),
    enabled: viewMode === 'review' && showReviewTab,
  })

  const sites = sitesData?.items ?? []
  const totalCount = sitesData?.total ?? sites.length
  const allInspections = inspectionsData?.items ?? []

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

  // Обходы для раскраски меток: инспектору — свои (бэкенд сам их так и
  // скопит), проверяющему/админу — по выбранному району, иначе на карте
  // всегда были только синие "необойдённые" точки независимо от реального
  // статуса — раскраска была реализована только для инспектора.
  // page_size=1000 — реальный максимум на бэкенде (Query(..., le=1000) в
  // list_inspections); запрос 5000 всегда падал 422 и молча оставлял карту
  // нераскрашенной даже для инспектора.
  const { data: myInspectionsData } = useQuery<{ total: number; items: InspectionOut[] }>({
    queryKey: ['my-inspections-map', effectiveDistrictFilter],
    queryFn: () => inspectionsApi.list({ page_size: 1000, district_id: effectiveDistrictFilter }),
    enabled: user?.role === 'inspector' || isReviewerLike,
  })
  const myInspections = myInspectionsData?.items ?? []

  // Карта: site_id → последний статус обхода
  const siteStatusMap = useMemo(() => {
    const map: Record<string, string> = {}
    const latestCreatedAt: Record<string, string> = {}
    for (const insp of myInspections) {
      if (!latestCreatedAt[insp.site_id] || insp.created_at > latestCreatedAt[insp.site_id]) {
        latestCreatedAt[insp.site_id] = insp.created_at
        map[insp.site_id] = insp.status
      }
    }
    return map
  }, [myInspections])

  // Фильтруем обходы по статусу
  const filteredInspections = allInspections.filter((insp) => {
    if (reviewStatusFilter === 'all') return true
    if (reviewStatusFilter === 'pending') return insp.status !== 'completed'
    return insp.status === reviewStatusFilter
  })

  const center: L.LatLngExpression = [55.829, 37.532]

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="bg-primary-800 text-white px-4 py-3 flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-lg font-bold">Обход площадок</h1>
          <p className="text-blue-200 text-xs">
            {user?.full_name}
            {user?.role === 'reviewer' && <span className="ml-1 text-amber-300">(проверяющий)</span>}
          </p>
        </div>
        <div className="flex gap-1">
          {user?.role === 'inspector' && (
            <button onClick={() => navigate('/my-inspections')} className="p-2 rounded-lg hover:bg-primary-700 transition-colors" title="История обходов">
              <History className="w-5 h-5" />
            </button>
          )}
          {/* Админ пользуется своими /admin/dashboard и /admin/issues через
              иконку "Админ-панель" ниже — не должен попадать на reviewer-
              роуты /dashboard и /issues (roles={['reviewer']} в App.tsx). */}
          {user?.role === 'reviewer' && (
            <>
              <button onClick={() => navigate('/dashboard')} className="p-2 rounded-lg hover:bg-primary-700 transition-colors" title="Дашборд">
                <BarChart3 className="w-5 h-5" />
              </button>
              <button onClick={() => navigate('/issues')} className="p-2 rounded-lg hover:bg-primary-700 transition-colors" title="Замечания">
                <AlertCircle className="w-5 h-5" />
              </button>
            </>
          )}
          {user?.role === 'admin' && (
            <button onClick={() => navigate('/admin')} className="p-2 rounded-lg hover:bg-primary-700 transition-colors" title="Админ-панель">
              <Users className="w-5 h-5" />
            </button>
          )}
          {user?.role !== 'inspector' && (
            <button onClick={() => toast.promise(reportsApi.exportXlsx({ district_id: districtFilter }), {
              loading: 'Готовлю файл...', success: 'Файл скачан', error: 'Ошибка выгрузки',
            })} className="p-2 rounded-lg hover:bg-primary-700 transition-colors" title="Выгрузка в Excel">
              <Download className="w-5 h-5" />
            </button>
          )}
          <button onClick={() => setShowFilters((v) => !v)} className="p-2 rounded-lg hover:bg-primary-700 transition-colors" title="Фильтры">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
            </svg>
          </button>
          <button onClick={() => navigate('/profile')} className="p-2 rounded-lg hover:bg-primary-700 transition-colors" title="Профиль">
            <UserCircle className="w-5 h-5" />
          </button>
          <button onClick={() => { logoutStore(); navigate('/login') }} className="p-2 rounded-lg hover:bg-primary-700 transition-colors" title="Выйти">
            <LogOut className="w-5 h-5" />
          </button>
        </div>
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
                Мои площадки
              </button>
            </div>
          )}
          {(user?.role === 'inspector' || isReviewerLike) && myInspections.length > 0 && (
            <div className="flex items-center gap-2">
              {user?.role === 'inspector' && (
                <button
                  onClick={() => setMyInspOnly(!myInspOnly)}
                  className={`text-xs px-3 py-1 rounded-full font-medium transition-colors ${
                    myInspOnly ? 'bg-primary-700 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  Только необойдённые
                </button>
              )}
              <button
                onClick={() => setShowLegend((v) => !v)}
                className="text-xs px-3 py-1 rounded-full bg-gray-100 text-gray-600 hover:bg-gray-200 font-medium"
              >
                Легенда
              </button>
              <span className="text-xs text-gray-400">
                Обойдено: {Object.values(siteStatusMap).filter((s) => s === 'completed' || s === 'issues_found').length}/{totalCount}
              </span>
            </div>
          )}
          {showLegend && (user?.role === 'inspector' || isReviewerLike) && (
            <div className="flex gap-3 text-xs text-gray-500 flex-wrap">
              <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-blue-600 inline-block" /> Не обойдена</span>
              <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-yellow-500 inline-block" /> В процессе</span>
              <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-green-600 inline-block" /> Завершена</span>
              <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-red-600 inline-block" /> С нарушениями</span>
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
            {allInspections.length > 0 && (
              <span className="text-xs ml-0.5">({allInspections.length})</span>
            )}
          </button>
        )}
      </div>

      {/* Фильтр статусов для режима проверки */}
      {viewMode === 'review' && showReviewTab && (
        <div className="bg-white border-b px-4 py-2 shrink-0 flex gap-2 overflow-x-auto">
          {[
            { key: 'all', label: `Все (${allInspections.length})` },
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
                Нажмите кнопку фильтров <span className="inline-block align-middle mx-0.5"><svg className="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" /></svg></span>
                в шапке и выберите район для отображения площадок.
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
            inspections={filteredInspections}
            emptyLabel={reviewStatusFilter !== 'all' ? 'Нет обходов с этим статусом' : 'Нет обходов для проверки'}
            onAccept={(id) => guardDemoAction(() => acceptInspectionMutation.mutate(id))}
            acceptPending={acceptInspectionMutation.isPending}
          />
        ) : viewMode === 'map' ? (
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
            <MarkerClusterGroup chunkedLoading maxClusterRadius={60} spiderfyOnMaxZoom>
              {sites.filter((s) => !myInspOnly || !siteStatusMap[s.id] || siteStatusMap[s.id] !== 'completed').map((s) => {
                const status = (user?.role === 'inspector' || isReviewerLike) ? siteStatusMap[s.id] : null
                const icon = s.type === CHILD_TYPE ? childIcon(status) : sportIcon(status)
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
                      <button onClick={() => navigate(`/sites/${s.id}`)} className="mt-2 text-xs btn-primary py-1 px-3 w-full flex items-center justify-center gap-1">
                        Открыть <ChevronRight className="w-3 h-3" />
                      </button>
                    </div>
                  </Popup>
                </Marker>
              })}
            </MarkerClusterGroup>
          </MapContainer>
        ) : (
          <div ref={listRef} onScroll={handleListScroll} className="overflow-y-auto h-full p-3 space-y-2">
            {sites.map((s) => (
              <button key={s.id} onClick={() => navigate(`/sites/${s.id}`)} className="card w-full text-left hover:border-primary-300 transition-colors">
                <div className="flex items-start gap-3">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-white text-lg shrink-0 ${s.type === CHILD_TYPE ? 'bg-blue-600' : 'bg-green-600'}`}>
                    {s.type === CHILD_TYPE ? 'Д' : 'С'}
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
                  </div>
                  <ChevronRight className="w-4 h-4 text-gray-300 shrink-0 mt-3" />
                </div>
              </button>
            ))}
            {sites.length === 0 && (<div className="text-center text-gray-400 py-12">Нет площадок</div>)}
          </div>
        )}
      </div>
    </div>
  )
}
