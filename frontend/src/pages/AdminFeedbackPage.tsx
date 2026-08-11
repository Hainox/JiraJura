import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { feedbackApi } from '@/lib/api'
import type { FeedbackReportOut, FeedbackStatus } from '@/types'
import { ArrowLeft, RefreshCw, MessageSquareWarning, Phone, MapPin, User as UserIcon } from 'lucide-react'
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

export default function AdminFeedbackPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [commentDraft, setCommentDraft] = useState('')

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['feedback', statusFilter],
    queryFn: () => feedbackApi.list({ status: statusFilter || undefined }),
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
              <span className={`badge text-xs ${STATUS_COLORS[r.status]}`}>{STATUS_LABELS[r.status]}</span>
              <span className="text-xs text-gray-400">{new Date(r.created_at).toLocaleString('ru')}</span>
            </div>
            <div className="text-sm text-gray-800 whitespace-pre-wrap">{r.message}</div>
            <div className="flex flex-wrap gap-3 text-xs text-gray-500">
              <span className="flex items-center gap-1"><UserIcon className="w-3.5 h-3.5" />{r.full_name || 'Аноним'}</span>
              {r.phone && <span className="flex items-center gap-1"><Phone className="w-3.5 h-3.5" />{r.phone}</span>}
              {r.location_text && <span className="flex items-center gap-1"><MapPin className="w-3.5 h-3.5" />{r.location_text}</span>}
            </div>

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
