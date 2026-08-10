import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { districtsApi, inspectionsApi } from '@/lib/api'
import type { DistrictOut, InspectionOut } from '@/types'
import { ArrowLeft, RefreshCw } from 'lucide-react'
import { notify as toast } from '@/lib/toast'
import InspectionReviewList from '@/components/InspectionReviewList'
import { guardDemoAction } from '@/stores/demoMode'

const STATUS_FILTERS = [
  { key: 'all', label: 'Все' },
  { key: 'pending', label: 'На проверку' },
  { key: 'completed', label: 'Принятые' },
  { key: 'issues_found', label: 'С нарушениями' },
  { key: 'critical', label: 'Критические' },
]

// Приёмка обходов для админа — отдельно от вкладки "Проверка" на карте
// (та осталась только для роли reviewer, см. MapPage.tsx). Та же бизнес-логика
// (список + кнопка "Принять"), но собственный роут/меню, не через reviewer-UI.
export default function AdminReviewsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [districtFilter, setDistrictFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')

  const { data: districts } = useQuery<DistrictOut[]>({
    queryKey: ['districts'],
    queryFn: districtsApi.list,
  })

  const { data, isLoading, refetch } = useQuery<{ total: number; items: InspectionOut[] }>({
    queryKey: ['inspections-admin-review', districtFilter],
    queryFn: () => inspectionsApi.list({ district_id: districtFilter || undefined, page_size: 200 }),
  })

  const acceptMutation = useMutation({
    mutationFn: (inspectionId: string) => inspectionsApi.update(inspectionId, { status: 'completed' }),
    onSuccess: () => {
      toast.success('Обход принят')
      queryClient.invalidateQueries({ queryKey: ['inspections-admin-review'] })
    },
    onError: () => toast.error('Не удалось принять обход'),
  })

  const allInspections = data?.items ?? []
  // Та же семантика фильтра, что и во вкладке "Проверка" на MapPage.tsx
  const filteredInspections = allInspections.filter((insp) => {
    if (statusFilter === 'all') return true
    if (statusFilter === 'pending') return insp.status !== 'completed'
    return insp.status === statusFilter
  })

  return (
    <div className="h-full flex flex-col bg-gray-50">
      <div className="bg-primary-800 text-white px-4 py-3 flex items-center gap-3 shrink-0">
        <button onClick={() => navigate('/admin')} className="p-1.5 rounded-lg hover:bg-primary-700 transition-colors">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex-1">
          <h1 className="text-lg font-bold">Приёмка обходов</h1>
          <p className="text-blue-200 text-xs">{allInspections.length} обходов</p>
        </div>
        <button onClick={() => refetch()} className="p-2 rounded-lg hover:bg-primary-700">
          <RefreshCw className="w-5 h-5" />
        </button>
      </div>

      <div className="bg-white border-b px-4 py-2 shrink-0 space-y-2">
        <select className="input-field text-sm w-full" value={districtFilter} onChange={(e) => setDistrictFilter(e.target.value)}>
          <option value="">Все районы</option>
          {districts?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        <div className="flex gap-2 overflow-x-auto">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setStatusFilter(f.key)}
              className={`shrink-0 px-3 py-1 text-xs rounded-full font-medium transition-colors ${
                statusFilter === f.key ? 'bg-primary-700 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 min-h-0">
        {isLoading ? (
          <div className="h-full flex items-center justify-center text-gray-400">Загрузка...</div>
        ) : (
          <InspectionReviewList
            inspections={filteredInspections}
            emptyLabel={statusFilter !== 'all' ? 'Нет обходов с этим статусом' : 'Нет обходов для проверки'}
            onAccept={(id) => guardDemoAction(() => acceptMutation.mutate(id))}
            acceptPending={acceptMutation.isPending}
          />
        )}
      </div>
    </div>
  )
}
