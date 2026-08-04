import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { MapContainer, TileLayer, Marker, Popup, useMap, AttributionControl } from 'react-leaflet'
import L from 'leaflet'
import { sitesApi, districtsApi, reportsApi, inspectionsApi } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { useTheme } from '@/lib/theme'
import type { SiteOut, DistrictOut, InspectionOut } from '@/types'
import { List, Map as MapIcon, LogOut, ChevronRight, Users, Download, ClipboardCheck, Clock, CheckCircle2, AlertTriangle, AlertCircle, Sun, Moon, UserCircle } from 'lucide-react'
import { notify as toast } from '@/lib/toast'
import 'leaflet/dist/leaflet.css'

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

const STATUS_LABELS: Record<string, string> = {
  planned: 'Запланирован', in_progress: 'В процессе', completed: 'Завершён',
  issues_found: 'Есть нарушения', critical: 'Критический',
}
const STATUS_COLORS: Record<string, string> = {
  in_progress: 'bg-blue-100 text-blue-800',
  completed: 'bg-green-100 text-green-800',
  issues_found: 'bg-orange-100 text-orange-800',
  critical: 'bg-red-100 text-red-800',
  planned: 'bg-gray-100 text-gray-600',
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
  const user = useAuthStore((s) => s.user)
  const logoutStore = useAuthStore((s) => s.logout)
  const [viewMode, setViewMode] = useState<'map' | 'list' | 'review'>('map')
  const [districtFilter, setDistrictFilter] = useState<string | undefined>()
  const [typeFilter, setTypeFilter] = useState<string | undefined>()
  const [showFilters, setShowFilters] = useState(false)
  const [reviewStatusFilter, setReviewStatusFilter] = useState<string>('all')
  const [myInspOnly, setMyInspOnly] = useState(false)
  const [showLegend, setShowLegend] = useState(false)

  const { theme, toggleTheme } = useTheme()

  const isAdmin = user?.role === 'admin'
  const isReviewerLike = user?.role === 'reviewer' || isAdmin

  const { data: districts } = useQuery<DistrictOut[]>({
    queryKey: ['districts'],
    queryFn: districtsApi.list,
  })

  const effectiveDistrictFilter = isAdmin ? districtFilter : (user?.district_id ?? districtFilter)

  const { data: sitesData } = useQuery({
    queryKey: ['sites', effectiveDistrictFilter, typeFilter],
    queryFn: () => sitesApi.list({ district_id: effectiveDistrictFilter, type: typeFilter, page_size: 5000 }),
  })

  // Загрузка обходов для режима проверки
  const { data: inspectionsData } = useQuery<{ total: number; items: InspectionOut[] }>({
    queryKey: ['inspections-review', effectiveDistrictFilter],
    queryFn: () => inspectionsApi.list({ page_size: 200 }),
    enabled: viewMode === 'review' && isReviewerLike,
  })

  const sites = sitesData?.items ?? []
  const totalCount = sitesData?.total ?? sites.length
  const allInspections = inspectionsData?.items ?? []

  // Для инспектора: загружаем его обходы чтобы раскрасить метки
  const { data: myInspectionsData } = useQuery<{ total: number; items: InspectionOut[] }>({
    queryKey: ['my-inspections-map', effectiveDistrictFilter],
    queryFn: () => inspectionsApi.list({ page_size: 5000 }),
    enabled: user?.role === 'inspector',
  })
  const myInspections = myInspectionsData?.items ?? []

  // Карта: site_id → последний статус обхода
  const siteStatusMap = useMemo(() => {
    const map: Record<string, string> = {}
    for (const insp of myInspections) {
      if (!map[insp.site_id] || insp.created_at > (myInspections.find((i) => i.site_id === insp.site_id && i.id === map[insp.site_id])?.created_at ?? '')) {
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
          {user?.role !== 'inspector' && (
            <button onClick={() => navigate('/issues')} className="p-2 rounded-lg hover:bg-primary-700 transition-colors" title="Замечания">
              <AlertCircle className="w-5 h-5" />
            </button>
          )}
          {user?.role === 'admin' && (
            <button onClick={() => navigate('/admin/users')} className="p-2 rounded-lg hover:bg-primary-700 transition-colors" title="Пользователи">
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
          <button onClick={toggleTheme} className="p-2 rounded-lg hover:bg-primary-700 transition-colors" title={theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}>
            {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
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
                <option value="">Все районы ({totalCount} площадок)</option>
                {districts?.map((d) => (<option key={d.id} value={d.id}>{d.name}</option>))}
              </select>
            ) : (
              <div className="input-field text-sm flex-1 flex items-center text-gray-700">
                {districts && districts.length > 0 ? districts[0].name : 'Район не назначен'}
              </div>
            )}
            <select className="input-field text-sm flex-1" value={typeFilter ?? ''} onChange={(e) => setTypeFilter(e.target.value || undefined)}>
              <option value="">Все типы</option>
              <option value={CHILD_TYPE}>Детские</option>
              <option value={SPORT_TYPE}>Спортивные</option>
            </select>
          </div>
          {user?.role === 'inspector' && myInspections.length > 0 && (
            <div className="flex items-center gap-2">
              <button
                onClick={() => setMyInspOnly((v) => !v)}
                className={`text-xs px-3 py-1 rounded-full font-medium transition-colors ${
                  myInspOnly ? 'bg-primary-700 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                Только необойдённые
              </button>
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
          {showLegend && user?.role === 'inspector' && (
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
        {isReviewerLike && (
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
      {viewMode === 'review' && isReviewerLike && (
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
        {viewMode === 'review' && isReviewerLike ? (
          <div className="overflow-y-auto h-full p-3 space-y-2">
            {filteredInspections.map((insp) => {
              const okCount = insp.answers?.filter((a) => a.result === 'ok').length ?? 0
              const defectCount = insp.answers?.filter((a) => a.result === 'defect').length ?? 0
              const total = insp.answers?.length ?? 0
              const isReviewed = !!insp.reviewed_by

              return (
                <button
                  key={insp.id}
                  onClick={() => navigate(`/inspections/${insp.id}`)}
                  className="card w-full text-left hover:border-primary-300 transition-colors"
                >
                  <div className="flex items-start gap-3">
                    <div className={`shrink-0 mt-0.5 ${
                      insp.status === 'critical' ? 'text-red-500' :
                      insp.status === 'issues_found' ? 'text-orange-500' :
                      insp.status === 'completed' ? 'text-green-500' : 'text-gray-400'
                    }`}>
                      {insp.status === 'completed' ? <CheckCircle2 className="w-5 h-5" /> :
                       insp.status === 'critical' ? <AlertTriangle className="w-5 h-5" /> :
                       <Clock className="w-5 h-5" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-sm truncate">
                          {insp.site?.courtyard?.name ?? 'Площадка'}
                        </span>
                        <span className={`badge text-xs ${STATUS_COLORS[insp.status] ?? 'bg-gray-100'}`}>
                          {STATUS_LABELS[insp.status] ?? insp.status}
                        </span>
                        {isReviewed && (
                          <span className="badge badge-ok text-xs">✓ Проверен</span>
                        )}
                      </div>
                      <div className="text-xs text-gray-500 mt-0.5">
                        {insp.site?.district?.name} • {insp.inspector?.full_name}
                      </div>
                      <div className="text-xs text-gray-400 mt-0.5">
                        {new Date(insp.created_at).toLocaleDateString('ru')} — {new Date(insp.created_at).toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' })}
                      </div>
                      {total > 0 && (
                        <div className="flex gap-3 mt-1.5 text-xs">
                          <span className="text-green-600">✓ {okCount} ОК</span>
                          {defectCount > 0 && <span className="text-red-600">✕ {defectCount} наруш.</span>}
                          <span className="text-gray-400">{total - okCount - defectCount} не пров.</span>
                          {insp.photos_count > 0 && <span className="text-gray-400">📷 {insp.photos_count}</span>}
                          {insp.issues_count > 0 && <span className="text-orange-600">⚠ {insp.issues_count} замечаний</span>}
                        </div>
                      )}
                      {insp.reviewed_by && (
                        <div className="text-xs text-amber-600 mt-1">
                          Проверил: {insp.reviewed_by.full_name}
                          {insp.reviewed_at && `, ${new Date(insp.reviewed_at).toLocaleDateString('ru')}`}
                        </div>
                      )}
                    </div>
                    <ChevronRight className="w-4 h-4 text-gray-300 shrink-0 mt-3" />
                  </div>
                </button>
              )
            })}
            {filteredInspections.length === 0 && (
              <div className="text-center text-gray-400 py-12">
                {reviewStatusFilter !== 'all' ? 'Нет обходов с этим статусом' : 'Нет обходов для проверки'}
              </div>
            )}
          </div>
        ) : viewMode === 'map' ? (
          <MapContainer center={center} zoom={12} className="h-full w-full" attributionControl={false}>
            <AttributionControl prefix={false} />
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              maxZoom={19}
            />
            <FitBounds data={sites} />
            {sites.filter((s) => !myInspOnly || !siteStatusMap[s.id] || siteStatusMap[s.id] !== 'completed').map((s) => {
              const status = user?.role === 'inspector' ? siteStatusMap[s.id] : null
              const icon = s.type === CHILD_TYPE ? childIcon(status) : sportIcon(status)
              return <Marker key={s.id} position={[s.lat ?? 55.829, s.lon ?? 37.532]} icon={icon}>
                <Popup>
                  <div className="min-w-[180px]">
                    <div className="font-semibold text-sm">{s.courtyard?.name ?? 'Площадка'}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{s.district?.name}</div>
                    <div className="text-xs text-gray-400 mt-0.5">
                      {s.type === CHILD_TYPE ? 'Детская' : 'Спортивная'} • {s.area_m2} м²
                    </div>
                    <button onClick={() => navigate(`/sites/${s.id}`)} className="mt-2 text-xs btn-primary py-1 px-3 w-full flex items-center justify-center gap-1">
                      Открыть <ChevronRight className="w-3 h-3" />
                    </button>
                  </div>
                </Popup>
              </Marker>
            })}
          </MapContainer>
        ) : (
          <div className="overflow-y-auto h-full p-3 space-y-2">
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
