import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { districtsApi, issuesApi } from '@/lib/api'
import type { DistrictOut, IssueOut } from '@/types'
import { ArrowLeft, RefreshCw, ShieldCheck, Camera, MapPin, ChevronRight } from 'lucide-react'

const CRIT_LABELS: Record<string, string> = { low: 'Низкая', medium: 'Средняя', high: 'Высокая', critical: 'Критическая' }
const CRIT_COLORS: Record<string, string> = {
  low: 'bg-gray-100 text-gray-600', medium: 'bg-blue-100 text-blue-700',
  high: 'bg-orange-100 text-orange-800', critical: 'bg-red-100 text-red-900 font-bold',
}

// Отдельная очередь "исправлено, ждёт решения админа" — до этой страницы
// такие замечания были видны только через общий список /admin/issues с
// ручным фильтром по статусу, из-за чего фактическое решение (принять
// закрыть или вернуть на доработку) никто не открывал: "Исправлено" в
// дешборде росло, а "Принято"/"На доработку" оставались нулём. Само
// решение принимается на IssueFixPage — сюда только сводка "что ждёт",
// чтобы не дублировать уже готовый разбор до/после.
export default function AdminIssueControlPage() {
  const navigate = useNavigate()
  const [districtFilter, setDistrictFilter] = useState('')

  const { data: districts } = useQuery<DistrictOut[]>({
    queryKey: ['districts'],
    queryFn: districtsApi.list,
  })

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['issues-final-control', districtFilter],
    queryFn: () => issuesApi.list({ status: 'fixed', district_id: districtFilter || undefined, page_size: 200 }),
  })

  const issues = data?.items ?? []

  return (
    <div className="h-full flex flex-col bg-gray-50">
      <div className="bg-primary-800 text-white px-4 py-3 flex items-center gap-3 shrink-0">
        <button onClick={() => navigate('/admin')} className="p-1.5 rounded-lg hover:bg-primary-700 transition-colors">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex-1">
          <h1 className="text-lg font-bold">Финальный контроль</h1>
          <p className="text-blue-200 text-xs">{issues.length} исправлений ждут решения</p>
        </div>
        <button onClick={() => refetch()} className="p-2 rounded-lg hover:bg-primary-700">
          <RefreshCw className="w-5 h-5" />
        </button>
      </div>

      <div className="bg-white border-b px-4 py-2 shrink-0">
        <select className="input-field text-sm w-full" value={districtFilter} onChange={(e) => setDistrictFilter(e.target.value)}>
          <option value="">Все районы</option>
          {districts?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
      </div>

      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="h-full flex items-center justify-center text-gray-400">Загрузка...</div>
        ) : issues.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-gray-400 gap-2 px-4 text-center">
            <ShieldCheck className="w-10 h-10 opacity-30" />
            Нет исправлений, ожидающих решения
          </div>
        ) : (
          <div className="divide-y">
            {issues.map((issue: IssueOut) => (
              <button
                key={issue.id}
                onClick={() => navigate(`/admin/issues/${issue.id}`, { state: { from: '/admin/control' } })}
                className="w-full text-left bg-white hover:bg-gray-50 transition-colors p-3 flex items-start gap-3"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className="font-semibold text-sm truncate">{issue.title}</span>
                    <span className={`badge text-xs ${CRIT_COLORS[issue.criticality] ?? 'bg-gray-100'}`}>
                      {CRIT_LABELS[issue.criticality] ?? issue.criticality}
                    </span>
                  </div>
                  <div className="text-xs text-gray-500 flex items-center gap-1 flex-wrap">
                    {issue.site_name && <span className="flex items-center gap-0.5"><MapPin className="w-3 h-3" />{issue.site_name}</span>}
                    {issue.district_name && <span className="text-gray-400">• {issue.district_name}</span>}
                  </div>
                  {issue.fix_comment && (
                    <div className="text-xs text-gray-600 mt-1.5 bg-green-50 rounded-lg px-2 py-1.5 line-clamp-2">
                      {issue.fix_comment}
                    </div>
                  )}
                  <div className="flex items-center gap-3 mt-1.5 text-xs text-gray-400">
                    {!!issue.fix_photos?.length && (
                      <span className="flex items-center gap-0.5"><Camera className="w-3 h-3" />{issue.fix_photos.length} фото исправления</span>
                    )}
                    {issue.assigned_user && <span>Исправил: {issue.assigned_user.full_name}</span>}
                  </div>
                </div>
                <ChevronRight className="w-4 h-4 text-gray-300 shrink-0 mt-1" />
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
