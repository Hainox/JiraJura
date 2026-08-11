import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { feedbackApi } from '@/lib/api'
import type { FeedbackReportOut, FeedbackStatus, FeedbackReportType } from '@/types'
import { ArrowLeft, RefreshCw, MessageSquareWarning, Phone, MapPin, User as UserIcon, Bug, HelpCircle, MapPinned, Paperclip } from 'lucide-react'
import { notify as toast } from '@/lib/toast'

const STATUS_LABELS: Record<FeedbackStatus, string> = {
  new: 'Новое', in_review: 'В работе', resolved: 'Решено', dismissed: 'Отклонено',
}
const STATUS_COLORS: Record<FeedbackStatus, string> = {
  new: 'bg-red-100 text-red-800',
  in_review: 'bg-yellow-100 text-yellow-800',
  resolved: 'bg-green-100 text-green-800',
  dismissed: 'bg-gray-100 text-gray-600',
}
const TYPE_LABELS: Record<FeedbackReportType, string> = {
  site: 'Площадка', app: 'Приложение', other: 'Другое',
}
const TYPE_ICONS: Record<FeedbackReportType, React.ReactNode> = {
  site: <MapPinned className="w-3.5 h-3.5" />,
  app: <Bug className="w-3.5 h-3.5" />,
  other: <HelpCircle className="w-3.5 h-3.5" />,
}
const TYPE_COLORS: Record<FeedbackReportType, string> = {
  site: 'bg-blue-100 text-blue-700',
  app: 'bg-purple-100 text-purple-700',
  other: 'bg-gray-100 text-gray-600',
}

export default function AdminFeedbackPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [typeFilter, setTypeFilter] = useState<string>('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [commentDraft, setCommentDraft] = useState('')

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['feedback', statusFilter, typeFilter],
    queryFn: () => feedbackApi.list({ status: statusFilter || undefined, report_type: typeFilter || undefined }),
  })

  const updateMutation = useMutation({
    mutationFn: (vars: { id: string; status?: string; admin_comment?: string }) =>
      feedbackApi.update(vars.id, { status: vars.status, admin_comment: vars.admin_comment }),
    onSuccess: () => {
      toast.success('Сохранено')
      queryClient.invalidateQueries({ queryKey: ['feedback'] })
      setEditingId(null)
    },
    onError: () => toast.error('Ошибка сохранения'),
  })

  const startEdit = (r: FeedbackReportOut) => {
    setEditingId(r.id)
    setCommentDraft(r.admin_comment ?? '')
  }

  return (
    <div className="h-full flex flex-col bg-gray-50">
      <div className="bg-primary-800 text-white px-4 py-3 flex items-center gap-3 shrink-0">
        <button onClick={() => navigate('/admin')} className="p-1.5 rounded-lg hover:bg-primary-700">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex-1">
          <h1 className="text-lg font-bold">Обращения</h1>
          <p className="text-blue-200 text-xs">Жалобы с публичной формы /feedback</p>
        </div>
        <button onClick={() => refetch()} className="p-2 rounded-lg hover:bg-primary-700">
          <RefreshCw className="w-5 h-5" />
        </button>
      </div>

      <div className="bg-white border-b px-4 py-2 shrink-0 flex gap-2">
        <select
          className="input-field text-sm flex-1"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">Все статусы</option>
          {(Object.keys(STATUS_LABELS) as FeedbackStatus[]).map((s) => (
            <option key={s} value={s}>{STATUS_LABELS[s]}</option>
          ))}
        </select>
        <select
          className="input-field text-sm flex-1"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
        >
          <option value="">Все типы</option>
          {(Object.keys(TYPE_LABELS) as FeedbackReportType[]).map((t) => (
            <option key={t} value={t}>{TYPE_LABELS[t]}</option>
          ))}
        </select>
      </div>

      <div className="overflow-y-auto flex-1 p-4 space-y-3">
        {isLoading && <div className="text-center text-gray-400 py-8">Загрузка...</div>}
        {data && data.items.length === 0 && (
          <div className="text-center text-gray-400 py-8 flex flex-col items-center gap-2">
            <MessageSquareWarning className="w-8 h-8" />
            Обращений нет
          </div>
        )}
        {data?.items.map((r) => (
          <div key={r.id} className="card space-y-2">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div className="flex items-center gap-1.5">
                <span className={`badge text-xs flex items-center gap-1 ${TYPE_COLORS[r.report_type]}`}>
                  {TYPE_ICONS[r.report_type]}{TYPE_LABELS[r.report_type]}
                </span>
                <span className={`badge text-xs ${STATUS_COLORS[r.status]}`}>{STATUS_LABELS[r.status]}</span>
              </div>
              <span className="text-xs text-gray-400">{new Date(r.created_at).toLocaleString('ru')}</span>
            </div>
            <div className="text-sm text-gray-800 whitespace-pre-wrap">{r.message}</div>
            <div className="flex flex-wrap gap-3 text-xs text-gray-500">
              <span className="flex items-center gap-1"><UserIcon className="w-3.5 h-3.5" />{r.full_name || 'Аноним'}</span>
              {r.phone && <span className="flex items-center gap-1"><Phone className="w-3.5 h-3.5" />{r.phone}</span>}
              {r.location_text && <span className="flex items-center gap-1"><MapPin className="w-3.5 h-3.5" />{r.location_text}</span>}
            </div>
            {r.attachments.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {r.attachments.map((a) => {
                  const isImage = a.content_type?.startsWith('image/')
                  return (
                    <a
                      key={a.id} href={a.url} target="_blank" rel="noreferrer"
                      className="flex items-center gap-1.5 border border-gray-200 rounded-lg px-2 py-1 hover:border-primary-300 transition-colors"
                    >
                      {isImage
                        ? <img src={a.url} alt="" className="w-8 h-8 object-cover rounded" />
                        : <Paperclip className="w-3.5 h-3.5 text-gray-400" />}
                      <span className="text-xs text-gray-600 max-w-[120px] truncate">{a.original_filename || 'файл'}</span>
                    </a>
                  )
                })}
              </div>
            )}

            {editingId === r.id ? (
              <div className="space-y-2 pt-2 border-t">
                <select
                  className="input-field text-sm"
                  defaultValue={r.status}
                  onChange={(e) => updateMutation.mutate({ id: r.id, status: e.target.value })}
                >
                  {(Object.keys(STATUS_LABELS) as FeedbackStatus[]).map((s) => (
                    <option key={s} value={s}>{STATUS_LABELS[s]}</option>
                  ))}
                </select>
                <textarea
                  className="input-field text-sm min-h-[70px]"
                  placeholder="Комментарий администратора"
                  value={commentDraft}
                  onChange={(e) => setCommentDraft(e.target.value)}
                />
                <div className="flex gap-2">
                  <button
                    className="btn-primary text-sm px-3 py-1.5"
                    onClick={() => updateMutation.mutate({ id: r.id, admin_comment: commentDraft })}
                  >
                    Сохранить комментарий
                  </button>
                  <button className="btn-outline text-sm px-3 py-1.5" onClick={() => setEditingId(null)}>
                    Отмена
                  </button>
                </div>
              </div>
            ) : (
              <div className="pt-1 border-t flex items-center justify-between gap-2">
                {r.admin_comment && <div className="text-xs text-gray-500 italic">{r.admin_comment}</div>}
                <button className="text-xs text-primary-600 font-medium ml-auto" onClick={() => startEdit(r)}>
                  Разобрать →
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
