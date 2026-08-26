import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { systemApi } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import type { SystemStatsOut, DeployEventOut } from '@/types'
import { notify as toast } from '@/lib/toast'
import {
  ArrowLeft, RefreshCw, Database, HardDrive, Clock, Server,
  Search, KeyRound, AlertTriangle, Rocket, CheckCircle2, XCircle, Loader2,
} from 'lucide-react'

const COUNT_LABELS: Record<string, string> = {
  users: 'Пользователи', districts: 'Районы', courtyards: 'Дворы',
  sites: 'Площадки', inspections: 'Обходы', issues: 'Замечания', photos: 'Фото',
}

const TABS = [
  { key: 'overview', label: 'Обзор' },
  { key: 'diagnostics', label: 'Диагностика' },
  { key: 'deploy', label: 'Деплой' },
] as const
type TabKey = typeof TABS[number]['key']

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return `${h} ч ${m} мин`
  return `${m} мин`
}

export default function AdminSystemPage() {
  const navigate = useNavigate()
  const isDeveloper = useAuthStore((s) => s.user?.is_developer)
  const [tab, setTab] = useState<TabKey>('overview')

  const { data, isLoading, isError, refetch } = useQuery<SystemStatsOut>({
    queryKey: ['system-stats'],
    queryFn: systemApi.stats,
    refetchInterval: 60_000,
    enabled: !!isDeveloper,
  })

  // Роут открыт всем admin (roles=['admin']), но сам раздел — только для
  // account'ов с is_developer: бэкенд и так вернёт 403 на /system/*,
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
          <p className="text-blue-200 text-xs">Эксплуатационные инструменты</p>
        </div>
        {tab === 'overview' && (
          <button onClick={() => refetch()} className="p-2 rounded-lg hover:bg-primary-700">
            <RefreshCw className="w-5 h-5" />
          </button>
        )}
      </div>

      <div className="flex border-b border-gray-200 bg-white shrink-0">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex-1 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              tab === t.key ? 'border-primary-600 text-primary-700' : 'border-transparent text-gray-400 hover:text-gray-600'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="overflow-y-auto flex-1 p-4 space-y-4">
        {tab === 'overview' && (
          isLoading ? (
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
          )
        )}

        {tab === 'diagnostics' && <DiagnosticsTab />}
        {tab === 'deploy' && <DeployTab />}
      </div>
    </div>
  )
}

/** Диагностика по клику — веб-версия diagnose_logins.py / diagnose_missing_required_photos.py,
 * чтобы не заходить по SSH ради типового разбора жалобы. Только чтение. */
function DiagnosticsTab() {
  const [address, setAddress] = useState('')
  const [district, setDistrict] = useState('')
  const [searched, setSearched] = useState(false)

  const loginsQuery = useQuery({
    queryKey: ['diagnostics-logins'],
    queryFn: systemApi.diagnosticsLogins,
  })

  const photosQuery = useQuery({
    queryKey: ['diagnostics-missing-photos', address, district],
    queryFn: () => systemApi.diagnosticsMissingPhotos(address, district || undefined),
    enabled: false,
  })

  const runPhotosSearch = () => {
    if (address.trim().length < 2) {
      toast.error('Введите хотя бы 2 символа адреса')
      return
    }
    setSearched(true)
    photosQuery.refetch()
  }

  return (
    <div className="space-y-4">
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-gray-800 flex items-center gap-1.5">
            <KeyRound className="w-4 h-4 text-primary-600" />Логины
          </h3>
          <button onClick={() => loginsQuery.refetch()} className="p-1.5 rounded hover:bg-gray-100 text-gray-400">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
        {loginsQuery.isLoading ? (
          <div className="text-center text-gray-400 py-6 text-sm">Загрузка...</div>
        ) : loginsQuery.isError || !loginsQuery.data ? (
          <div className="text-center text-gray-400 py-6 text-sm">Не удалось загрузить</div>
        ) : (
          <div className="space-y-3 text-sm">
            <div className="text-gray-500">Всего пользователей: {loginsQuery.data.total_users}</div>

            {loginsQuery.data.broken_password_hash.length > 0 ? (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                <div className="font-medium text-red-800 mb-1 flex items-center gap-1.5">
                  <AlertTriangle className="w-4 h-4" />Повреждённый хэш пароля: {loginsQuery.data.broken_password_hash.length}
                </div>
                {loginsQuery.data.broken_password_hash.map((u) => (
                  <div key={u.id} className="text-red-700 text-xs py-0.5">{u.login} — {u.full_name} ({u.role})</div>
                ))}
                <div className="text-xs text-red-600 mt-1">Сброс пароля — только по SSH (diagnose_logins.py --apply), из UI не делаем.</div>
              </div>
            ) : (
              <div className="text-green-700 text-xs flex items-center gap-1.5"><CheckCircle2 className="w-3.5 h-3.5" />Повреждённых хэшей нет</div>
            )}

            {loginsQuery.data.inactive_not_soft_deleted.length > 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                <div className="font-medium text-amber-800 mb-1">Деактивированы не через софт-делит: {loginsQuery.data.inactive_not_soft_deleted.length}</div>
                {loginsQuery.data.inactive_not_soft_deleted.map((u, i) => (
                  <div key={i} className="text-amber-700 text-xs py-0.5">{u.login} — {u.full_name}</div>
                ))}
              </div>
            )}

            {loginsQuery.data.pending_registrations.length > 0 && (
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                <div className="font-medium text-gray-700 mb-1">Приглашения без завершённой регистрации: {loginsQuery.data.pending_registrations.length}</div>
                {loginsQuery.data.pending_registrations.slice(0, 20).map((u, i) => (
                  <div key={i} className="text-gray-600 text-xs py-0.5">{u.login} — {u.full_name}, истекает {new Date(u.expires_at).toLocaleString('ru')}</div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="card">
        <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-1.5">
          <Search className="w-4 h-4 text-primary-600" />Не хватает фото по адресу
        </h3>
        <div className="space-y-2 mb-3">
          <input
            className="input-field text-sm"
            placeholder="Адрес двора, например «Расковой»"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && runPhotosSearch()}
          />
          <input
            className="input-field text-sm"
            placeholder="Район (необязательно)"
            value={district}
            onChange={(e) => setDistrict(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && runPhotosSearch()}
          />
          <button onClick={runPhotosSearch} disabled={photosQuery.isFetching} className="btn-primary w-full py-2 text-sm">
            {photosQuery.isFetching ? 'Ищу...' : 'Найти'}
          </button>
        </div>

        {searched && !photosQuery.isFetching && photosQuery.data && (
          photosQuery.data.sites.length === 0 ? (
            <div className="text-center text-gray-400 py-4 text-sm">Площадок по этому адресу не найдено</div>
          ) : (
            <div className="space-y-3">
              {photosQuery.data.sites.map((site) => (
                <div key={site.site_id} className="border border-gray-200 rounded-lg p-3">
                  <div className="font-medium text-gray-800 text-sm mb-2">
                    {site.courtyard_name} ({site.type}), {site.district_name}
                  </div>
                  {site.inspections.length === 0 ? (
                    <div className="text-xs text-gray-400">Обходов нет</div>
                  ) : (
                    <div className="space-y-2">
                      {site.inspections.map((insp) => (
                        <div key={insp.id} className="text-xs bg-gray-50 rounded-lg p-2">
                          <div className="flex items-center justify-between text-gray-600">
                            <span>{insp.inspector_name} · {insp.status} · {insp.reviewed ? 'проверен' : 'не проверен'}</span>
                            <span>{new Date(insp.created_at).toLocaleDateString('ru')}</span>
                          </div>
                          {insp.missing_checklist_items.length > 0 ? (
                            <div className="text-red-600 mt-1">⚠ Не хватает фото: {insp.missing_checklist_items.join(', ')}</div>
                          ) : (
                            <div className="text-green-600 mt-1">✓ Все requires_photo-пункты имеют фото</div>
                          )}
                          {insp.photos.length > 0 && (
                            <div className="text-gray-500 mt-1">
                              Фото: {insp.photos.map((p) => `${p.label} (${new Date(p.created_at).toLocaleString('ru')})`).join('; ')}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )
        )}
      </div>
    </div>
  )
}

/** Деплой одной кнопкой — пишет маркер в audit_log, реальные git pull/build/
 * up/alembic выполняет отдельный watcher на хосте (deploy/scripts/deploy-watcher.sh,
 * см. deploy/README.md, п.10). api ничего не исполняет сам. */
function DeployTab() {
  const queryClient = useQueryClient()
  const [confirming, setConfirming] = useState(false)
  const [note, setNote] = useState('')

  const statusQuery = useQuery({
    queryKey: ['deploy-status'],
    queryFn: systemApi.deployStatus,
    refetchInterval: 10_000,
  })

  const requestMutation = useMutation({
    mutationFn: () => systemApi.requestDeploy(note || undefined),
    onSuccess: () => {
      setConfirming(false)
      setNote('')
      toast.success('Деплой запрошен — сервер подхватит маркер в течение минуты')
      queryClient.invalidateQueries({ queryKey: ['deploy-status'] })
    },
    onError: () => toast.error('Не удалось отправить запрос на деплой'),
  })

  return (
    <div className="space-y-4">
      <div className="card">
        <h3 className="font-semibold text-gray-800 mb-2 flex items-center gap-1.5">
          <Rocket className="w-4 h-4 text-primary-600" />Деплой
        </h3>
        <p className="text-xs text-gray-500 mb-3">
          Запускает на сервере тот же набор команд, что и ручное обновление:
          git pull, пересборку, перезапуск, применение миграций. Занимает
          обычно 1-3 минуты; результат появится в истории ниже.
        </p>
        {!confirming ? (
          <button onClick={() => setConfirming(true)} className="btn-primary w-full py-2.5 flex items-center justify-center gap-2">
            <Rocket className="w-4 h-4" />Запросить деплой
          </button>
        ) : (
          <div className="space-y-2">
            <input
              className="input-field text-sm"
              placeholder="Комментарий (необязательно) — что именно деплоите"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <div className="flex gap-2">
              <button onClick={() => setConfirming(false)} className="btn-outline flex-1 py-2">Отмена</button>
              <button
                onClick={() => requestMutation.mutate()}
                disabled={requestMutation.isPending}
                className="btn-primary flex-1 py-2 flex items-center justify-center gap-2"
              >
                {requestMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Rocket className="w-4 h-4" />}
                Подтвердить
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="card">
        <h3 className="font-semibold text-gray-800 mb-3">История</h3>
        {statusQuery.isLoading ? (
          <div className="text-center text-gray-400 py-6 text-sm">Загрузка...</div>
        ) : !statusQuery.data || statusQuery.data.events.length === 0 ? (
          <div className="text-center text-gray-400 py-6 text-sm">Запросов на деплой ещё не было</div>
        ) : (
          <div className="space-y-2">
            {statusQuery.data.events.map((ev) => (
              <DeployEventRow key={ev.id} event={ev} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function DeployEventRow({ event }: { event: DeployEventOut }) {
  let details: { note?: string; ok?: boolean; log_tail?: string; requested_by_login?: string } | null = null
  try {
    details = event.details ? JSON.parse(event.details) : null
  } catch {
    details = null
  }

  const isRequest = event.action === 'deploy_requested'
  const isCompleted = event.action === 'deploy_completed'
  const ok = details?.ok

  return (
    <div className="text-xs bg-gray-50 rounded-lg p-2.5">
      <div className="flex items-center gap-1.5 font-medium text-gray-700">
        {isRequest && <Loader2 className="w-3.5 h-3.5 text-blue-500" />}
        {isCompleted && ok && <CheckCircle2 className="w-3.5 h-3.5 text-green-600" />}
        {isCompleted && !ok && <XCircle className="w-3.5 h-3.5 text-red-600" />}
        <span>
          {isRequest ? `Запрошен деплой${details?.requested_by_login ? ` — ${details.requested_by_login}` : ''}` : null}
          {isCompleted ? (ok ? 'Деплой завершён успешно' : 'Деплой завершился с ошибкой') : null}
        </span>
        <span className="text-gray-400 ml-auto">{new Date(event.created_at).toLocaleString('ru')}</span>
      </div>
      {isRequest && details?.note && <div className="text-gray-500 mt-1">Комментарий: {details.note}</div>}
      {isCompleted && details?.log_tail && (
        <details className="mt-1">
          <summary className="text-gray-400 cursor-pointer">Лог</summary>
          <pre className="whitespace-pre-wrap text-[10px] text-gray-500 mt-1 max-h-40 overflow-y-auto">{details.log_tail}</pre>
        </details>
      )}
    </div>
  )
}
