import { Navigate, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { systemApi } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import type { SystemStatsOut } from '@/types'
import { ArrowLeft, RefreshCw, Database, HardDrive, Clock, Server } from 'lucide-react'

const COUNT_LABELS: Record<string, string> = {
  users: 'Пользователи', districts: 'Районы', courtyards: 'Дворы',
  sites: 'Площадки', inspections: 'Обходы', issues: 'Замечания', photos: 'Фото',
}

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return `${h} ч ${m} мин`
  return `${m} мин`
}

export default function AdminSystemPage() {
  const navigate = useNavigate()
  const isDeveloper = useAuthStore((s) => s.user?.is_developer)
  const { data, isLoading, isError, refetch } = useQuery<SystemStatsOut>({
    queryKey: ['system-stats'],
    queryFn: systemApi.stats,
    refetchInterval: 60_000,
    enabled: !!isDeveloper,
  })

  // Роут открыт всем admin (roles=['admin']), но сам раздел — только для
  // account'ов с is_developer: бэкенд и так вернёт 403 на /system/stats,
  // но без этого редиректа обычный админ, зашедший по прямой ссылке,
  // увидел бы просто общую ошибку загрузки вместо понятного объяснения.
  if (!isDeveloper) return <Navigate to="/admin" replace />

  return (
    <div className="h-full flex flex-col bg-gray-50">
      <div className="bg-primary-800 text-white px-4 py-3 flex items-center gap-3 shrink-0">
        <button onClick={() => navigate('/admin')} className="p-1.5 rounded-lg hover:bg-primary-700">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex-1">
          <h1 className="text-lg font-bold">Разработчик</h1>
          <p className="text-blue-200 text-xs">Эксплуатационная сводка</p>
        </div>
        <button onClick={() => refetch()} className="p-2 rounded-lg hover:bg-primary-700">
          <RefreshCw className="w-5 h-5" />
        </button>
      </div>

      <div className="overflow-y-auto flex-1 p-4 space-y-4">
        {isLoading ? (
          <div className="text-center text-gray-400 py-12">Загрузка...</div>
        ) : isError || !data ? (
          <div className="text-center text-gray-400 py-12">Не удалось загрузить сводку</div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div className="card p-3 flex items-center gap-3">
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-white shrink-0 ${data.db_ok ? 'bg-green-500' : 'bg-red-500'}`}>
                  <Database className="w-5 h-5" />
                </div>
                <div className="min-w-0">
                  <div className="text-xs text-gray-400">База данных</div>
                  <div className="text-sm font-bold text-gray-800">{data.db_ok ? 'В порядке' : 'Ошибка'}</div>
                </div>
              </div>
              <div className="card p-3 flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-indigo-500 flex items-center justify-center text-white shrink-0">
                  <Server className="w-5 h-5" />
                </div>
                <div className="min-w-0">
                  <div className="text-xs text-gray-400">Окружение</div>
                  <div className="text-sm font-bold text-gray-800">{data.app_env}</div>
                </div>
              </div>
              <div className="card p-3 flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-blue-500 flex items-center justify-center text-white shrink-0">
                  <Clock className="w-5 h-5" />
                </div>
                <div className="min-w-0">
                  <div className="text-xs text-gray-400">Аптайм процесса</div>
                  <div className="text-sm font-bold text-gray-800">{formatUptime(data.uptime_seconds)}</div>
                </div>
              </div>
              <div className="card p-3 flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-amber-500 flex items-center justify-center text-white shrink-0">
                  <HardDrive className="w-5 h-5" />
                </div>
                <div className="min-w-0">
                  <div className="text-xs text-gray-400">Папка uploads</div>
                  <div className="text-sm font-bold text-gray-800">{data.uploads_size_mb} МБ</div>
                </div>
              </div>
            </div>

            <div className="card">
              <h3 className="font-semibold text-gray-800 mb-3">Записей в базе</h3>
              <div className="space-y-2">
                {Object.entries(data.counts).map(([key, value]) => (
                  <div key={key} className="flex items-center justify-between text-sm">
                    <span className="text-gray-500">{COUNT_LABELS[key] ?? key}</span>
                    <span className="font-semibold text-gray-800 tabular-nums">{value.toLocaleString('ru')}</span>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
