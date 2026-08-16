import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { ArrowLeft, RefreshCw, LogIn, ShieldAlert } from 'lucide-react'

const REASON_LABELS: Record<string, string> = {
  user_not_found: 'логин не найден',
  inactive: 'аккаунт деактивирован',
  bad_password: 'неверный пароль',
}

interface LoginEntry {
  id: string
  user_name?: string
  action: string
  details?: string
  created_at: string
}

export default function LoginHistoryPage() {
  const navigate = useNavigate()
  const [loginFilter, setLoginFilter] = useState('')
  const [ipFilter, setIpFilter] = useState('')
  const [resultFilter, setResultFilter] = useState('')
  const [page, setPage] = useState(1)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['login-history', loginFilter, ipFilter, resultFilter, page],
    queryFn: async () => {
      const params: Record<string, string> = { page: String(page), page_size: '50' }
      if (loginFilter.trim()) params.login = loginFilter.trim()
      if (ipFilter.trim()) params.ip = ipFilter.trim()
      if (resultFilter) params.result = resultFilter
      const res = await api.get('/audit/logins', { params })
      return res.data as { total: number; items: LoginEntry[] }
    },
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / 50)

  const parseDetails = (details?: string) => {
    if (!details) return { login: '', ip: '', reason: '' }
    try {
      const d = JSON.parse(details)
      return { login: d.login ?? '', ip: d.ip ?? '', reason: d.reason ?? '' }
    } catch {
      return { login: '', ip: '', reason: '' }
    }
  }

  return (
    <div className="h-full flex flex-col bg-gray-50">
      <div className="bg-primary-800 text-white px-4 py-3 flex items-center gap-3 shrink-0">
        <button onClick={() => navigate('/admin')} data-prefetch="/admin" className="p-1.5 rounded-lg hover:bg-primary-700">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex-1">
          <h1 className="text-lg font-bold">История входов</h1>
          <p className="text-blue-200 text-xs">{total} записей</p>
        </div>
        <button onClick={() => refetch()} className="p-2 rounded-lg hover:bg-primary-700">
          <RefreshCw className="w-5 h-5" />
        </button>
      </div>

      <div className="bg-white border-b px-4 py-2 shrink-0 space-y-2">
        <div className="flex gap-2">
          <input
            className="input-field text-sm flex-1"
            placeholder="Фильтр по логину"
            value={loginFilter}
            onChange={(e) => { setLoginFilter(e.target.value); setPage(1) }}
          />
          <input
            className="input-field text-sm flex-1"
            placeholder="Фильтр по IP"
            value={ipFilter}
            onChange={(e) => { setIpFilter(e.target.value); setPage(1) }}
          />
        </div>
        <select
          className="input-field text-sm w-full"
          value={resultFilter}
          onChange={(e) => { setResultFilter(e.target.value); setPage(1) }}
        >
          <option value="">Все результаты</option>
          <option value="success">Успешные входы</option>
          <option value="failed">Неудачные попытки</option>
        </select>
      </div>

      <div className="overflow-y-auto flex-1">
        {isLoading ? (
          <div className="text-center text-gray-400 py-12">Загрузка...</div>
        ) : items.length === 0 ? (
          <div className="text-center text-gray-400 py-12">Нет записей входов</div>
        ) : (
          <div className="divide-y">
            {items.map((entry) => {
              const { login, ip, reason } = parseDetails(entry.details)
              const success = entry.action === 'login_success'
              return (
                <div key={entry.id} className="px-4 py-2.5 hover:bg-gray-50 transition-colors">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        {success
                          ? <LogIn className="w-4 h-4 text-green-600 shrink-0" />
                          : <ShieldAlert className="w-4 h-4 text-red-500 shrink-0" />}
                        <span className="font-medium text-sm text-gray-800 truncate">{login || '—'}</span>
                        <span className={`text-xs px-1.5 py-0.5 rounded-full shrink-0 ${success ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-600'}`}>
                          {success ? 'успешно' : 'неудачно'}
                        </span>
                      </div>
                      <div className="text-xs text-gray-400 mt-0.5 truncate">
                        {ip && <span className="text-gray-500">{ip}</span>}
                        {!success && reason && (
                          <span className="text-red-400"> — {REASON_LABELS[reason] ?? reason}</span>
                        )}
                      </div>
                    </div>
                    <div className="text-xs text-gray-400 shrink-0 text-right">
                      {entry.user_name && <div className="text-gray-500">{entry.user_name}</div>}
                      <div>{new Date(entry.created_at).toLocaleString('ru')}</div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {totalPages > 1 && (
        <div className="bg-white border-t px-4 py-2 shrink-0 flex justify-between">
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} className="px-3 py-1 text-sm rounded-lg border disabled:opacity-30">← Назад</button>
          <span className="text-sm text-gray-500">{page}/{totalPages}</span>
          <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages} className="px-3 py-1 text-sm rounded-lg border disabled:opacity-30">Вперёд →</button>
        </div>
      )}
    </div>
  )
}
