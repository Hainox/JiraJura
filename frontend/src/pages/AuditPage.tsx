import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, RefreshCw } from 'lucide-react'

const ACTION_LABELS: Record<string, string> = {
  invite_create: 'Создано приглашение',
  user_update: 'Пользователь изменён',
  user_delete: 'Пользователь удалён',
  inspection_review: 'Обход проверен',
  issue_update: 'Замечание изменено',
}

export default function AuditPage() {
  const navigate = useNavigate()
  const [actionFilter, setActionFilter] = useState('')
  const [page, setPage] = useState(1)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['audit', actionFilter, page],
    queryFn: async () => {
      const token = localStorage.getItem('access_token')
      const params = new URLSearchParams({ page: String(page), page_size: '50' })
      if (actionFilter) params.set('action', actionFilter)
      const res = await fetch(`/api/v1/audit/?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      return res.json() as Promise<{
        total: number
        items: { id: string; user_name?: string; action: string; entity_type: string; entity_id?: string; details?: string; created_at: string }[]
      }>
    },
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / 50)

  return (
    <div className="h-full flex flex-col bg-gray-50 dark:bg-gray-900">
      <div className="bg-primary-800 text-white px-4 py-3 flex items-center gap-3 shrink-0">
        <button onClick={() => navigate('/')} className="p-1.5 rounded-lg hover:bg-primary-700">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex-1">
          <h1 className="text-lg font-bold">Аудит действий</h1>
          <p className="text-blue-200 text-xs">{total} записей</p>
        </div>
        <button onClick={() => refetch()} className="p-2 rounded-lg hover:bg-primary-700">
          <RefreshCw className="w-5 h-5" />
        </button>
      </div>

      <div className="bg-white dark:bg-gray-800 border-b px-4 py-2 shrink-0">
        <select className="input-field text-sm" value={actionFilter} onChange={(e) => { setActionFilter(e.target.value); setPage(1) }}>
          <option value="">Все действия</option>
          {Object.entries(ACTION_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>

      <div className="overflow-y-auto flex-1">
        {isLoading ? (
          <div className="text-center text-gray-400 py-12">Загрузка...</div>
        ) : items.length === 0 ? (
          <div className="text-center text-gray-400 py-12">Нет записей аудита</div>
        ) : (
          <div className="divide-y dark:divide-gray-700">
            {items.map((entry) => (
              <div key={entry.id} className="px-4 py-2.5 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-gray-800 dark:text-gray-200">
                      <span className="font-medium">{ACTION_LABELS[entry.action] ?? entry.action}</span>
                      <span className="text-gray-400 mx-1">•</span>
                      <span className="text-gray-500 dark:text-gray-400">{entry.entity_type}</span>
                    </div>
                    {entry.details && (
                      <div className="text-xs text-gray-400 mt-0.5 truncate">
                        {(() => { try { return JSON.stringify(JSON.parse(entry.details), null, 0) } catch { return entry.details } })()}
                      </div>
                    )}
                  </div>
                  <div className="text-xs text-gray-400 shrink-0 text-right">
                    {entry.user_name && <div className="text-gray-500 dark:text-gray-400">{entry.user_name}</div>}
                    <div>{new Date(entry.created_at).toLocaleString('ru')}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {totalPages > 1 && (
        <div className="bg-white dark:bg-gray-800 border-t px-4 py-2 shrink-0 flex justify-between">
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} className="px-3 py-1 text-sm rounded-lg border disabled:opacity-30">← Назад</button>
          <span className="text-sm text-gray-500">{page}/{totalPages}</span>
          <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages} className="px-3 py-1 text-sm rounded-lg border disabled:opacity-30">Вперёд →</button>
        </div>
      )}
    </div>
  )
}
