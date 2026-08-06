import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { issuesApi, districtsApi, authApi } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import type { IssueOut, DistrictOut, UserAdminOut } from '@/types'
import { ArrowLeft, Search, Filter, RefreshCw, UserPlus, Calendar, Clock, AlertTriangle, CheckCircle2, XCircle, Wrench, ExternalLink } from 'lucide-react'
import { notify as toast } from '@/lib/toast'

const STATUS_LABELS: Record<string, string> = {
  open: 'Открыто', assigned: 'Назначено', in_work: 'В работе',
  fixed: 'Исправлено', control: 'На контроле', closed: 'Закрыто', overdue: 'Просрочено',
  revision_needed: 'На доработке',
}
const STATUS_COLORS: Record<string, string> = {
  open: 'bg-red-100 text-red-800',
  assigned: 'bg-blue-100 text-blue-800',
  in_work: 'bg-yellow-100 text-yellow-800',
  fixed: 'bg-green-100 text-green-800',
  control: 'bg-purple-100 text-purple-800',
  closed: 'bg-gray-100 text-gray-600',
  overdue: 'bg-red-200 text-red-900',
  revision_needed: 'bg-orange-100 text-orange-800',
}
const STATUS_ICONS: Record<string, React.ReactNode> = {
  open: <AlertTriangle className="w-4 h-4 text-red-500" />,
  assigned: <UserPlus className="w-4 h-4 text-blue-500" />,
  in_work: <Wrench className="w-4 h-4 text-yellow-600" />,
  fixed: <CheckCircle2 className="w-4 h-4 text-green-500" />,
  control: <RefreshCw className="w-4 h-4 text-purple-500" />,
  closed: <XCircle className="w-4 h-4 text-gray-400" />,
  overdue: <Clock className="w-4 h-4 text-red-600" />,
  revision_needed: <RefreshCw className="w-4 h-4 text-orange-500" />,
}
const CRIT_LABELS: Record<string, string> = {
  low: 'Низкая', medium: 'Средняя', high: 'Высокая', critical: 'Критическая',
}
const CRIT_COLORS: Record<string, string> = {
  low: 'bg-gray-100 text-gray-600',
  medium: 'bg-blue-100 text-blue-700',
  high: 'bg-orange-100 text-orange-800',
  critical: 'bg-red-100 text-red-900 font-bold',
}

export default function IssuesPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const isAdmin = user?.role === 'admin'

  const [statusFilter, setStatusFilter] = useState<string>('')
  const [criticalityFilter, setCriticalityFilter] = useState<string>('')
  const [districtFilter, setDistrictFilter] = useState<string>('')
  const [searchTerm, setSearchTerm] = useState('')
  const [page, setPage] = useState(1)

  const [editingIssue, setEditingIssue] = useState<string | null>(null)
  const [editStatus, setEditStatus] = useState('')
  const [editAssigned, setEditAssigned] = useState('')
  const [editDueDate, setEditDueDate] = useState('')

  const { data: districts } = useQuery<DistrictOut[]>({
    queryKey: ['districts'],
    queryFn: districtsApi.list,
  })

  const canAssign = isAdmin || user?.role === 'reviewer'

  const { data: usersData } = useQuery<UserAdminOut[]>({
    queryKey: ['users'],
    queryFn: authApi.listUsers,
    enabled: canAssign,
  })

  const effectiveDistrict = isAdmin ? (districtFilter || undefined) : (user?.district_id ?? undefined)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['issues', statusFilter, criticalityFilter, effectiveDistrict, page],
    queryFn: () => issuesApi.list({
      status: statusFilter || undefined,
      criticality: criticalityFilter || undefined,
      district_id: effectiveDistrict,
      page,
      page_size: 20,
    }),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, ...data }: { id: string; status?: string; assigned_to?: string | null; due_date?: string; comment?: string }) =>
      issuesApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['issues'] })
      toast.success('Замечание обновлено')
      setEditingIssue(null)
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(msg || 'Ошибка обновления')
    },
  })

  const issues = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / 20)

  // локальный поиск (по уже загруженным)
  const filteredIssues = searchTerm
    ? issues.filter((i) =>
        i.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
        i.site_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        i.district_name?.toLowerCase().includes(searchTerm.toLowerCase())
      )
    : issues

  const handleStatusChange = (issue: IssueOut) => {
    setEditingIssue(issue.id)
    setEditStatus(issue.status)
    setEditAssigned(issue.assigned_to ?? '')
    setEditDueDate(issue.due_date?.slice(0, 10) ?? '')
  }

  const saveChanges = (issueId: string) => {
    updateMutation.mutate({
      id: issueId,
      status: editStatus || undefined,
      // явный null, а не undefined — иначе "Не назначен" молча ничего не
      // делает: undefined-поле axios/JSON.stringify просто выбрасывает из
      // тела запроса, и бэкенд не отличает это от "поле не трогали"
      assigned_to: editAssigned || null,
      // due_date на бэкенде — DATE, не datetime; input[type=date] уже даёт
      // "YYYY-MM-DD" — .toISOString() только добавлял риск сдвига на день
      // и был причиной 500 на любое сохранение с указанным сроком
      due_date: editDueDate || undefined,
    })
  }

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* Header */}
      <div className="bg-primary-800 text-white px-4 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/')} className="p-1.5 rounded-lg hover:bg-primary-700 transition-colors">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-lg font-bold">Замечания</h1>
            <p className="text-blue-200 text-xs">{total} замечаний</p>
          </div>
        </div>
        <button onClick={() => refetch()} className="p-2 rounded-lg hover:bg-primary-700 transition-colors">
          <RefreshCw className="w-5 h-5" />
        </button>
      </div>

      {/* Filters */}
      <div className="bg-white border-b px-4 py-2 shrink-0 space-y-2">
        <div className="flex gap-2">
          {isAdmin && (
            <select className="input-field text-sm flex-1" value={districtFilter} onChange={(e) => { setDistrictFilter(e.target.value); setPage(1) }}>
              <option value="">Все районы</option>
              {districts?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          )}
          <select className="input-field text-sm flex-1" value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }}>
            <option value="">Все статусы</option>
            <option value="open">Открыто</option>
            <option value="assigned">Назначено</option>
            <option value="in_work">В работе</option>
            <option value="fixed">Исправлено</option>
            <option value="control">На контроле</option>
            <option value="closed">Закрыто</option>
            <option value="overdue">Просрочено</option>
          </select>
          <select className="input-field text-sm flex-1" value={criticalityFilter} onChange={(e) => { setCriticalityFilter(e.target.value); setPage(1) }}>
            <option value="">Все критичности</option>
            <option value="low">Низкая</option>
            <option value="medium">Средняя</option>
            <option value="high">Высокая</option>
            <option value="critical">Критическая</option>
          </select>
        </div>
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            className="input-field text-sm pl-9 w-full"
            placeholder="Поиск по названию, площадке, району..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="text-center text-gray-400 py-12">Загрузка...</div>
        ) : filteredIssues.length === 0 ? (
          <div className="text-center text-gray-400 py-12">
            <AlertTriangle className="w-10 h-10 mx-auto mb-2 opacity-30" />
            Нет замечаний
            {(statusFilter || criticalityFilter || districtFilter) && (
              <div className="text-xs mt-1">Попробуйте изменить фильтры</div>
            )}
          </div>
        ) : (
          <div className="divide-y">
            {filteredIssues.map((issue) => (
              <div key={issue.id} className="bg-white hover:bg-gray-50 transition-colors">
                <div className="p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-sm truncate">{issue.title}</span>
                        <span className={`badge text-xs ${CRIT_COLORS[issue.criticality] ?? 'bg-gray-100'}`}>
                          {CRIT_LABELS[issue.criticality] ?? issue.criticality}
                        </span>
                        <span className={`badge text-xs flex items-center gap-0.5 ${STATUS_COLORS[issue.status] ?? 'bg-gray-100'}`}>
                          {STATUS_ICONS[issue.status]}
                          {STATUS_LABELS[issue.status] ?? issue.status}
                        </span>
                      </div>

                      <div className="text-xs text-gray-500 mt-1">
                        {issue.site_name}
                        {issue.district_name && <span className="mx-1">•</span>}
                        {issue.district_name && <span className="text-gray-400">{issue.district_name}</span>}
                      </div>

                      <div className="flex items-center gap-3 mt-1 text-xs text-gray-400 flex-wrap">
                        {issue.creator && (
                          <span>Создал: {issue.creator.full_name}</span>
                        )}
                        {issue.assigned_user && (
                          <span className="text-blue-600">→ {issue.assigned_user.full_name}</span>
                        )}
                        {!issue.assigned_user && issue.assigned_to && (
                          <span className="text-gray-400">Назначен</span>
                        )}
                        {issue.due_date && (
                          <span className={new Date(issue.due_date) < new Date() ? 'text-red-600 font-medium' : ''}>
                            <Calendar className="w-3 h-3 inline mr-0.5" />
                            до {new Date(issue.due_date).toLocaleDateString('ru')}
                          </span>
                        )}
                        <span>
                          {new Date(issue.created_at).toLocaleDateString('ru')}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        onClick={() => navigate(`/inspections/${issue.inspection_id}`)}
                        className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors text-gray-400 hover:text-gray-600"
                        title="Открыть обход"
                      >
                        <ExternalLink className="w-4 h-4" />
                      </button>
                      {(user?.role === 'reviewer' || isAdmin) && (
                        <>
                          <button
                            onClick={() => navigate(`/issues/${issue.id}`)}
                            className="p-1.5 rounded-lg hover:bg-green-100 transition-colors text-green-600 hover:text-green-700"
                            title="Зафиксировать исправление"
                          >
                            <Wrench className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => handleStatusChange(issue)}
                            className="btn-primary text-xs py-1 px-2 flex items-center gap-1"
                          >
                            <Filter className="w-3 h-3" />
                            Изменить
                          </button>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Inline edit form */}
                  {editingIssue === issue.id && (
                    <div className="mt-3 pt-3 border-t space-y-2">
                      <div className="flex gap-2">
                        <select
                          className="input-field text-sm flex-1"
                          value={editStatus}
                          onChange={(e) => setEditStatus(e.target.value)}
                        >
                          {Object.entries(STATUS_LABELS)
                            // "Исправлено" (с фото) → "Принято"/"На доработке" — решает
                            // только админ и только через IssueFixPage (нужны фото
                            // устранения и, для доработки, комментарий — эта форма
                            // их не собирает)
                            .filter(([k]) => k !== 'revision_needed' && k !== 'closed')
                            .map(([k, v]) => (
                              <option key={k} value={k}>{v}</option>
                            ))}
                        </select>
                        {canAssign && (
                          <select
                            className="input-field text-sm flex-1"
                            value={editAssigned}
                            onChange={(e) => setEditAssigned(e.target.value)}
                          >
                            <option value="">Не назначен</option>
                            {usersData?.map((u) => (
                              <option key={u.id} value={u.id}>{u.full_name}</option>
                            ))}
                          </select>
                        )}
                      </div>
                      <div className="flex gap-2">
                        <input
                          type="date"
                          className="input-field text-sm flex-1"
                          value={editDueDate}
                          onChange={(e) => setEditDueDate(e.target.value)}
                        />
                      </div>
                      <div className="flex gap-2 justify-end">
                        <button
                          onClick={() => setEditingIssue(null)}
                          className="px-3 py-1.5 text-sm rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50"
                        >
                          Отмена
                        </button>
                        <button
                          onClick={() => saveChanges(issue.id)}
                          disabled={updateMutation.isPending}
                          className="px-3 py-1.5 text-sm rounded-lg bg-primary-700 text-white hover:bg-primary-800 disabled:opacity-50"
                        >
                          Сохранить
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Description */}
                  {issue.description && (
                    <div className="mt-2 text-xs text-gray-600 bg-gray-50 rounded p-2">
                      {issue.description}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="bg-white border-t px-4 py-2 shrink-0 flex items-center justify-between">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1 text-sm rounded-lg border border-gray-200 disabled:opacity-30 hover:bg-gray-50"
          >
            ← Назад
          </button>
          <span className="text-sm text-gray-500">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="px-3 py-1 text-sm rounded-lg border border-gray-200 disabled:opacity-30 hover:bg-gray-50"
          >
            Вперёд →
          </button>
        </div>
      )}
    </div>
  )
}
