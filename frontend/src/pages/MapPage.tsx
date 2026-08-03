import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { MapContainer, TileLayer, GeoJSON, Marker, Popup, useMap, AttributionControl } from 'react-leaflet'
import L from 'leaflet'
import { sitesApi, districtsApi } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import type { SiteOut, DistrictOut } from '@/types'
import { List, Map as MapIcon, LogOut, ChevronRight, Users } from 'lucide-react'
import 'leaflet/dist/leaflet.css'

// Иконки по типу площадок
const childIcon = L.divIcon({
  className: 'custom-icon',
  html: `<div style="background:#2563eb;color:white;width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;box-shadow:0 2px 6px rgba(0,0,0,.3)">Д</div>`,
  iconSize: [24, 24],
  iconAnchor: [12, 12],
})

const sportIcon = L.divIcon({
  className: 'custom-icon',
  html: `<div style="background:#16a34a;color:white;width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;box-shadow:0 2px 6px rgba(0,0,0,.3)">С</div>`,
  iconSize: [24, 24],
  iconAnchor: [12, 12],
})

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
  const [viewMode, setViewMode] = useState<'map' | 'list'>('map')
  const [districtFilter, setDistrictFilter] = useState<string | undefined>()
  const [showFilters, setShowFilters] = useState(false)

  const { data: districts } = useQuery<DistrictOut[]>({
    queryKey: ['districts'],
    queryFn: districtsApi.list,
  })

  const { data: sitesData } = useQuery({
    queryKey: ['sites', districtFilter],
    queryFn: () => sitesApi.list({ district_id: districtFilter }),
  })

  const sites = sitesData?.items ?? []

  const center: L.LatLngExpression = [55.829, 37.532] // САО

  // GeoJSON-представление для карты — используем реальные lat/lon из API
  const geoPoints = sites
    .filter((s) => s.lat != null && s.lon != null)
    .map((s) => ({
      type: 'Feature' as const,
      geometry: { type: 'Point' as const, coordinates: [s.lon!, s.lat!] },
      properties: { id: s.id, name: s.courtyard?.name ?? '', type: s.type },
    }))

  const geoData: GeoJSON.FeatureCollection = {
    type: 'FeatureCollection',
    features: geoPoints,
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="bg-primary-800 text-white px-4 py-3 flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-lg font-bold">Обход площадок</h1>
          <p className="text-blue-200 text-xs">{user?.full_name}</p>
        </div>
        <div className="flex gap-1">
          {user?.role === 'admin' && (
            <button
              onClick={() => navigate('/admin/users')}
              className="p-2 rounded-lg hover:bg-primary-700 transition-colors"
              title="Пользователи"
            >
              <Users className="w-5 h-5" />
            </button>
          )}
          <button
            onClick={() => setShowFilters((v) => !v)}
            className="p-2 rounded-lg hover:bg-primary-700 transition-colors"
            title="Фильтры"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
            </svg>
          </button>
          <button
            onClick={() => { logoutStore(); navigate('/login') }}
            className="p-2 rounded-lg hover:bg-primary-700 transition-colors"
            title="Выйти"
          >
            <LogOut className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Фильтр по районам */}
      {showFilters && (
        <div className="bg-white border-b px-4 py-2 shrink-0">
          <select
            className="input-field text-sm"
            value={districtFilter ?? ''}
            onChange={(e) => setDistrictFilter(e.target.value || undefined)}
          >
            <option value="">Все районы ({sites.length} площадок)</option>
            {districts?.map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
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
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0">
        {viewMode === 'map' ? (
          <MapContainer center={center} zoom={12} className="h-full w-full" attributionControl={false}>
            {/* prefix={false} убирает стандартную приписку Leaflet; обязательная
                подпись OpenStreetMap (условие использования их тайлов) остаётся */}
            <AttributionControl prefix={false} />
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              maxZoom={19}
            />
            <FitBounds data={sites} />
            <GeoJSON key={districtFilter ?? 'all'} data={geoData} />
            {sites.map((s) => (
              <Marker
                key={s.id}
                position={[s.lat ?? 55.829, s.lon ?? 37.532]}
                icon={s.type === 'children' ? childIcon : sportIcon}
              >
                <Popup>
                  <div className="min-w-[180px]">
                    <div className="font-semibold text-sm">{s.courtyard?.name ?? 'Площадка'}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{s.district?.name}</div>
                    <div className="text-xs text-gray-400 mt-0.5">
                      {s.type === 'children' ? 'Детская' : 'Спортивная'} • {s.area_m2} м²
                    </div>
                    <button
                      onClick={() => navigate(`/sites/${s.id}`)}
                      className="mt-2 text-xs btn-primary py-1 px-3 w-full flex items-center justify-center gap-1"
                    >
                      Открыть <ChevronRight className="w-3 h-3" />
                    </button>
                  </div>
                </Popup>
              </Marker>
            ))}
          </MapContainer>
        ) : (
          <div className="overflow-y-auto h-full p-3 space-y-2">
            {sites.map((s) => (
              <button
                key={s.id}
                onClick={() => navigate(`/sites/${s.id}`)}
                className="card w-full text-left hover:border-primary-300 transition-colors"
              >
                <div className="flex items-start gap-3">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-white text-lg shrink-0 ${
                    s.type === 'children' ? 'bg-blue-600' : 'bg-green-600'
                  }`}>
                    {s.type === 'children' ? 'Д' : 'С'}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-sm truncate">{s.courtyard?.name ?? 'Площадка'}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{s.district?.name}</div>
                    <div className="text-xs text-gray-400 mt-0.5">
                      {s.type === 'children' ? 'Детская площадка' : 'Спортивная площадка'}
                      {' • '}{s.area_m2} м²
                    </div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-gray-300 shrink-0 mt-3" />
                </div>
              </button>
            ))}
            {sites.length === 0 && (
              <div className="text-center text-gray-400 py-12">Нет площадок</div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
