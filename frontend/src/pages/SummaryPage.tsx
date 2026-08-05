import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { inspectionsApi, checklistsApi } from '@/lib/api'
import type { InspectionOut } from '@/types'
import { ArrowLeft, AlertTriangle, FileText } from 'lucide-react'

const STATUS_LABELS: Record<string, string> = {
  planned: 'Запланирован', in_progress: 'В процессе',
  completed: 'Завершён', issues_found: 'Есть нарушения', critical: 'Критический',
}

export default function SummaryPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const inspectionId = id!

  const { data: inspection, isLoading } = useQuery<InspectionOut>({
    queryKey: ['inspection', inspectionId],
    queryFn: () => inspectionsApi.get(inspectionId),
    enabled: !!inspectionId,
  })

  const { data: template } = useQuery({
    queryKey: ['checklist-template', inspection?.site?.type],
    queryFn: () => checklistsApi.template({ site_type: inspection!.site.type }),
    enabled: !!inspection?.site?.type,
  })
  const questionByItemId = new Map((template ?? []).flatMap((t) => t.items).map((item) => [item.id, item.question]))

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
  const defectCount = answers.filter((a) => a.result === 'defect').length
  const total = answers.length

  return (
    <div className="h-full flex flex-col bg-gray-50">
      <div className="bg-primary-800 text-white px-4 py-3 flex items-center gap-3 shrink-0">
        <button onClick={() => navigate(`/sites/${inspection.site_id}`)} className="p-1 -ml-1 hover:bg-primary-700 rounded-lg">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <h1 className="font-bold text-lg">Сводка обхода</h1>
          <p className="text-blue-200 text-xs">
            {inspection.site?.courtyard?.name} • {STATUS_LABELS[inspection.status] ?? inspection.status}
          </p>
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
              <div className="text-2xl font-bold text-red-700">{defectCount}</div>
              <div className="text-xs text-red-600 mt-0.5">Нарушений</div>
            </div>
            <div className="bg-gray-100 rounded-xl p-3 text-center">
              <div className="text-2xl font-bold text-gray-500">{total - okCount - defectCount}</div>
              <div className="text-xs text-gray-500 mt-0.5">Не проверено</div>
            </div>
          </div>
        </div>

        {/* Нарушения */}
        {defectCount > 0 && (
          <div className="card">
            <h2 className="font-semibold text-red-700 mb-3 flex items-center gap-1.5">
              <AlertTriangle className="w-4 h-4" />
              Нарушения ({defectCount})
            </h2>
            <div className="space-y-2">
              {answers
                .filter((a) => a.result === 'defect')
                .map((a) => (
                  <div key={a.id} className="bg-red-50 rounded-lg p-3 text-sm">
                    <div className="text-red-800">{questionByItemId.get(a.checklist_item_id) ?? a.checklist_item_id}</div>
                    {a.comment && (
                      <div className="text-red-600 text-xs mt-1 italic">{a.comment}</div>
                    )}
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* Ссылка на полный обход */}
        <button
          onClick={() => navigate(`/inspections/${inspectionId}`)}
          className="btn-primary w-full flex items-center justify-center gap-2"
        >
          <FileText className="w-4 h-4" />
          Открыть полный обход
        </button>
      </div>
    </div>
  )
}
