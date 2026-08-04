import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { inspectionsApi, issuesApi } from '@/lib/api'
import type { InspectionOut, IssueOut } from '@/types'
import {
  ArrowLeft, AlertTriangle,
  FileText, Send
} from 'lucide-react'
import { notify as toast } from '@/lib/toast'

export default function SummaryPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const inspectionId = id!

  const [comment, setComment] = useState('')

  const { data: inspection, isLoading } = useQuery<InspectionOut>({
    queryKey: ['inspection', inspectionId],
    queryFn: () => inspectionsApi.get(inspectionId),
    enabled: !!inspectionId,
  })

  const { data: issuesData } = useQuery({
    queryKey: ['issues', inspectionId],
    queryFn: () => issuesApi.list({ site_id: undefined }),
    enabled: !!inspectionId,
  })

  const issues = issuesData?.items ?? []

  const completeMutation = useMutation({
    mutationFn: () =>
      inspectionsApi.complete(inspectionId, {
        status: 'completed',
        comment: comment || undefined,
      }),
    onSuccess: () => {
      toast.success('Обход завершён!')
      navigate('/')
    },
    onError: () => toast.error('Ошибка при завершении'),
  })

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50">
        <div className="text-gray-400">Загрузка...</div>
      </div>
    )
  }

  if (!inspection) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50">
        <div className="text-gray-400">Обход не найден</div>
      </div>
    )
  }

  const answers = inspection.answers ?? []
  const okCount = answers.filter((a) => a.result === 'ok').length
  const nokCount = answers.filter((a) => a.result === 'not_ok' || a.result === 'not ok').length
  const total = answers.length

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* Header */}
      <div className="bg-primary-800 text-white px-4 py-3 flex items-center gap-3 shrink-0">
        <button onClick={() => navigate(`/inspections/${inspectionId}`)} className="p-1 -ml-1 hover:bg-primary-700 rounded-lg">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <h1 className="font-bold text-lg">Сводка обхода</h1>
          <p className="text-blue-200 text-xs">{inspection.site?.courtyard?.name}</p>
        </div>
      </div>

      <div className="overflow-y-auto flex-1 p-4 space-y-4">
        {/* Статистика */}
        <div className="card">
          <h2 className="font-semibold text-gray-800 mb-3">Результаты проверки</h2>
          <div className="grid grid-cols-3 gap-2">
            <div className="bg-green-50 rounded-xl p-3 text-center">
              <div className="text-2xl font-bold text-green-700">{okCount}</div>
              <div className="text-xs text-green-600 mt-0.5">В порядке</div>
            </div>
            <div className="bg-red-50 rounded-xl p-3 text-center">
              <div className="text-2xl font-bold text-red-700">{nokCount}</div>
              <div className="text-xs text-red-600 mt-0.5">Нарушений</div>
            </div>
            <div className="bg-gray-100 rounded-xl p-3 text-center">
              <div className="text-2xl font-bold text-gray-500">{total - okCount - nokCount}</div>
              <div className="text-xs text-gray-500 mt-0.5">Не проверено</div>
            </div>
          </div>
        </div>

        {/* Нарушения */}
        {nokCount > 0 && (
          <div className="card">
            <h2 className="font-semibold text-red-700 mb-3 flex items-center gap-1.5">
              <AlertTriangle className="w-4 h-4" />
              Нарушения ({nokCount})
            </h2>
            <div className="space-y-2">
              {answers
                .filter((a) => a.result === 'not_ok' || a.result === 'not ok')
                .map((a) => (
                  <div key={a.id} className="bg-red-50 rounded-lg p-3 text-sm">
                    <div className="text-red-800">{a.checklist_item_id}</div>
                    {a.comment && (
                      <div className="text-red-600 text-xs mt-1 italic">{a.comment}</div>
                    )}
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* Замечания */}
        {issues.length > 0 && (
          <div className="card">
            <h2 className="font-semibold text-orange-700 mb-3 flex items-center gap-1.5">
              <FileText className="w-4 h-4" />
              Замечания ({issues.length})
            </h2>
            <div className="space-y-2">
              {issues.map((issue: IssueOut) => (
                <div key={issue.id} className="bg-orange-50 rounded-lg p-3 text-sm">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`badge text-[10px] ${
                      issue.criticality === 'critical' ? 'badge-nok' :
                      issue.criticality === 'high' ? 'bg-orange-100 text-orange-800' :
                      'bg-yellow-100 text-yellow-800'
                    }`}>
                      {issue.criticality === 'critical' ? 'Критическая' :
                       issue.criticality === 'high' ? 'Высокая' :
                       issue.criticality === 'medium' ? 'Средняя' : 'Низкая'}
                    </span>
                  </div>
                  <div className="font-medium text-gray-800">{issue.title}</div>
                  {issue.description && (
                    <div className="text-gray-600 text-xs mt-0.5">{issue.description}</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Комментарий */}
        <div className="card">
          <h2 className="font-semibold text-gray-800 mb-3">Завершение обхода</h2>
          <label className="label">Комментарий к обходу</label>
          <textarea
            className="input-field text-sm"
            rows={3}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Общие замечания по обходу..."
          />
        </div>
      </div>

      {/* Кнопка отправки */}
      <div className="p-4 bg-white border-t shrink-0">
        <button
          onClick={() => completeMutation.mutate()}
          disabled={completeMutation.isPending}
          className="btn-primary w-full py-3 text-base flex items-center justify-center gap-2"
        >
          <Send className="w-5 h-5" />
          {completeMutation.isPending ? 'Отправка...' : 'Завершить обход'}
        </button>
      </div>
    </div>
  )
}
