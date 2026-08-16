import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { inspectionsApi } from '@/lib/api'
import type { InspectionOut } from '@/types'
import { ArrowLeft } from 'lucide-react'

const STATUS_LABELS: Record<string, string> = {
  planned: 'Запланирован', in_progress: 'В процессе',
  completed: 'Завершён', issues_found: 'Есть нарушения', critical: 'Критический',
}
const STATUS_COLORS: Record<string, string> = {
  in_progress: 'bg-blue-100 text-blue-800',
  completed: 'bg-green-100 text-green-800',
  issues_found: 'bg-orange-100 text-orange-800',
  critical: 'bg-red-100 text-red-800',
  planned: 'bg-gray-100 text-gray-600',
}

function dayLabel(dateStr: string): string {
  const d = new Date(dateStr)
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString()
  if (sameDay(d, today)) return 'Сегодня'
  if (sameDay(d, yesterday)) return 'Вчера'
  return d.toLocaleDateString('ru', { day: 'numeric', month: 'long' })
}

export default function MyInspectionsPage() {
  const navigate = useNavigate()

  // Бэкенд сам ограничивает список только своими обходами для роли
  // inspector (см. list_inspections) — отдельный district_id/inspector_id
  // передавать не нужно.
  const { data, isLoading } = useQuery<{ total: number; items: InspectionOut[] }>({
    queryKey: ['my-inspections-history'],
    queryFn: () => inspectionsApi.list({ page_size: 500 }),
  })

  const inspections = data?.items ?? []

  // Зависим от data?.items, а не от производного `inspections ?? []`: тот
  // пересоздаётся каждый рендер (новый [] при каждом обращении), и useMemo
  // с таким списком зависимостей пересчитывался бы на каждый рендер впустую.
  // data из react-query ссылочно стабилен между рендерами.
  const todayCount = useMemo(() => {
    const today = new Date().toDateString()
    return (data?.items ?? []).filter((i) => new Date(i.created_at).toDateString() === today).length
  }, [data?.items])

  const grouped = useMemo(() => {
    const groups: Record<string, InspectionOut[]> = {}
    for (const insp of data?.items ?? []) {
      const key = dayLabel(insp.created_at)
      if (!groups[key]) groups[key] = []
      groups[key].push(insp)
    }
    return groups
  }, [data?.items])

  return (
    <div className="h-full flex flex-col bg-gray-50">
      <div className="bg-primary-800 text-white px-4 py-3 flex items-center gap-3 shrink-0">
        <button onClick={() => navigate('/')} className="p-1.5 rounded-lg hover:bg-primary-700 transition-colors">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <h1 className="text-lg font-bold">История обходов</h1>
          <p className="text-blue-200 text-xs">Сегодня пройдено: {todayCount}</p>
        </div>
      </div>

      <div className="overflow-y-auto flex-1 p-4 space-y-4">
        {isLoading ? (
          <div className="text-center text-gray-400 py-12">Загрузка...</div>
        ) : inspections.length === 0 ? (
          <div className="text-center text-gray-400 py-12">Обходов пока нет</div>
        ) : (
          Object.entries(grouped).map(([day, items]) => (
            <div key={day}>
              <h2 className="text-xs font-semibold text-gray-500 uppercase mb-2">{day} ({items.length})</h2>
              <div className="space-y-2">
                {items.map((insp) => (
                  <button
                    key={insp.id}
                    onClick={() => navigate(`/inspections/${insp.id}`)}
                    className="card w-full text-left hover:border-primary-300 transition-colors"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="font-semibold text-sm truncate">{insp.site?.courtyard?.name ?? 'Площадка'}</div>
                        <div className="text-xs text-gray-500 mt-0.5 truncate">{insp.site?.district?.name}</div>
                        <div className="text-xs text-gray-400 mt-0.5">
                          {new Date(insp.created_at).toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' })}
                        </div>
                      </div>
                      <span className={`badge text-xs shrink-0 ${STATUS_COLORS[insp.status] ?? 'bg-gray-100'}`}>
                        {STATUS_LABELS[insp.status] ?? insp.status}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
