import { useNavigate } from 'react-router-dom'
import { ChevronRight, Check, CheckCircle2, AlertTriangle, Clock } from 'lucide-react'
import type { InspectionOut } from '@/types'

const STATUS_LABELS: Record<string, string> = {
  planned: 'Запланирован', in_progress: 'В процессе', completed: 'Завершён',
  issues_found: 'Есть нарушения', critical: 'Критический',
}
const STATUS_COLORS: Record<string, string> = {
  in_progress: 'bg-blue-100 text-blue-800',
  completed: 'bg-green-100 text-green-800',
  issues_found: 'bg-orange-100 text-orange-800',
  critical: 'bg-red-100 text-red-800',
  planned: 'bg-gray-100 text-gray-600',
}

// Список обходов на приёмку — общий для вкладки "Проверка" у проверяющего
// (MapPage) и отдельного экрана "Приёмка обходов" у админа (AdminReviewsPage).
export default function InspectionReviewList({
  inspections, emptyLabel, onAccept, acceptPending,
}: {
  inspections: InspectionOut[]
  emptyLabel: string
  onAccept: (inspectionId: string) => void
  acceptPending: boolean
}) {
  const navigate = useNavigate()

  return (
    <div className="overflow-y-auto h-full p-3 space-y-2">
      {inspections.map((insp) => {
        const okCount = insp.answers?.filter((a) => a.result === 'ok').length ?? 0
        const defectCount = insp.answers?.filter((a) => a.result === 'defect').length ?? 0
        const total = insp.answers?.length ?? 0
        const isReviewed = !!insp.reviewed_by
        const isGreen = insp.status === 'completed' && (insp.issues_count ?? 0) === 0

        return (
          <div
            key={insp.id}
            role="button"
            tabIndex={0}
            onClick={() => navigate(`/inspections/${insp.id}`)}
            onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/inspections/${insp.id}`) }}
            className="card w-full text-left hover:border-primary-300 transition-colors cursor-pointer"
          >
            <div className="flex items-start gap-3">
              <div className={`shrink-0 mt-0.5 ${
                insp.status === 'critical' ? 'text-red-500' :
                insp.status === 'issues_found' ? 'text-orange-500' :
                insp.status === 'completed' ? 'text-green-500' : 'text-gray-400'
              }`}>
                {insp.status === 'completed' ? <CheckCircle2 className="w-5 h-5" /> :
                 insp.status === 'critical' ? <AlertTriangle className="w-5 h-5" /> :
                 <Clock className="w-5 h-5" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-sm truncate">
                    {insp.site?.courtyard?.name ?? 'Площадка'}
                  </span>
                  <span className={`badge text-xs ${STATUS_COLORS[insp.status] ?? 'bg-gray-100'}`}>
                    {STATUS_LABELS[insp.status] ?? insp.status}
                  </span>
                  {isReviewed && (
                    <span className="badge badge-ok text-xs">✓ Проверен</span>
                  )}
                </div>
                <div className="text-xs text-gray-500 mt-0.5">
                  {insp.site?.district?.name} • {insp.inspector?.full_name}
                </div>
                <div className="text-xs text-gray-400 mt-0.5">
                  {new Date(insp.created_at).toLocaleDateString('ru')} — {new Date(insp.created_at).toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' })}
                </div>
                {total > 0 && (
                  <div className="flex gap-3 mt-1.5 text-xs">
                    <span className="text-green-600">✓ {okCount} ОК</span>
                    {defectCount > 0 && <span className="text-red-600">✕ {defectCount} наруш.</span>}
                    <span className="text-gray-400">{total - okCount - defectCount} не пров.</span>
                    {insp.photos_count > 0 && <span className="text-gray-400">📷 {insp.photos_count}</span>}
                    {insp.issues_count > 0 && <span className="text-orange-600">⚠ {insp.issues_count} замечаний</span>}
                  </div>
                )}
                {insp.reviewed_by && (
                  <div className="text-xs text-amber-600 mt-1">
                    Проверил: {insp.reviewed_by.full_name}
                    {insp.reviewed_at && `, ${new Date(insp.reviewed_at).toLocaleDateString('ru')}`}
                  </div>
                )}
                {isGreen && !isReviewed && (
                  <button
                    onClick={(e) => { e.stopPropagation(); onAccept(insp.id) }}
                    disabled={acceptPending}
                    className="mt-2 btn-primary text-xs py-1.5 px-3 flex items-center gap-1 disabled:opacity-50"
                  >
                    <Check className="w-3.5 h-3.5" />
                    Принять
                  </button>
                )}
              </div>
              <ChevronRight className="w-4 h-4 text-gray-300 shrink-0 mt-3" />
            </div>
          </div>
        )
      })}
      {inspections.length === 0 && (
        <div className="text-center text-gray-400 py-12">{emptyLabel}</div>
      )}
    </div>
  )
}
