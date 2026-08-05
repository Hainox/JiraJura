import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { reportsApi, api } from '@/lib/api'
import { ArrowLeft, RefreshCw, TrendingUp, MapPin, AlertTriangle, CheckCircle2, Clock, Users, Building, FileSpreadsheet } from 'lucide-react'
import { notify as toast } from '@/lib/toast'

interface DashboardData {
  total_sites: number; total_inspections_week: number; total_inspections_month: number
  inspections_in_progress: number; inspections_reviewed: number; inspections_pending_review: number
  issues_open: number; issues_overdue: number; inspectors_count: number; reviewers_count: number
}

interface DistrictStat { district_name: string; total_sites: number; inspected: number; percent: number }

export default function DashboardPage() {
  const navigate = useNavigate()
  const [showDistricts, setShowDistricts] = useState(false)

  const { data, isLoading, refetch } = useQuery<DashboardData>({
    queryKey: ['dashboard'],
    queryFn: async () => {
      const res = await api.get('/dashboard/')
      return res.data
    },
  })

  const { data: districts } = useQuery<DistrictStat[]>({
    queryKey: ['dashboard-districts'],
    queryFn: async () => {
      const res = await api.get('/dashboard/districts')
      return res.data
    },
    enabled: showDistricts,
  })

  const exportXlsx = () => {
    toast.promise(reportsApi.exportXlsx(), {
      loading: 'Готовлю файл...', success: 'Отчёт скачан', error: 'Ошибка выгрузки',
    })
  }

  if (isLoading) return <div className="h-full flex items-center justify-center text-gray-400">Загрузка...</div>

  return (
    <div className="h-full flex flex-col bg-gray-50 dark:bg-gray-900">
      <div className="bg-primary-800 text-white px-4 py-3 flex items-center gap-3 shrink-0">
        <button onClick={() => navigate('/')} className="p-1.5 rounded-lg hover:bg-primary-700"><ArrowLeft className="w-5 h-5" /></button>
        <div className="flex-1"><h1 className="text-lg font-bold">Дашборд</h1></div>
        <button onClick={() => refetch()} className="p-2 rounded-lg hover:bg-primary-700"><RefreshCw className="w-5 h-5" /></button>
      </div>

      <div className="overflow-y-auto flex-1 p-4 space-y-4">
        {/* KPI cards */}
        <div className="grid grid-cols-2 gap-3">
          <StatCard icon={<Building className="w-5 h-5" />} label="Площадок" value={data?.total_sites ?? 0} color="bg-blue-500" />
          <StatCard icon={<TrendingUp className="w-5 h-5" />} label="Обходов за мес." value={data?.total_inspections_month ?? 0} color="bg-green-500" />
          <StatCard icon={<Clock className="w-5 h-5" />} label="В процессе" value={data?.inspections_in_progress ?? 0} color="bg-yellow-500" />
          <StatCard icon={<CheckCircle2 className="w-5 h-5" />} label="Проверено" value={data?.inspections_reviewed ?? 0} color="bg-green-600" />
          <StatCard icon={<AlertTriangle className="w-5 h-5" />} label="На проверке" value={data?.inspections_pending_review ?? 0} color="bg-orange-500" />
          <StatCard icon={<AlertTriangle className="w-5 h-5" />} label="Замечаний (откр.)" value={data?.issues_open ?? 0} color="bg-red-500" />
          <StatCard icon={<Users className="w-5 h-5" />} label="Инспекторов" value={data?.inspectors_count ?? 0} color="bg-purple-500" />
          <StatCard icon={<Users className="w-5 h-5" />} label="Проверяющих" value={data?.reviewers_count ?? 0} color="bg-indigo-500" />
        </div>

        {/* Quick actions */}
        <div className="flex gap-2">
          <button onClick={exportXlsx} className="btn-primary flex-1 flex items-center justify-center gap-2 text-sm py-2">
            <FileSpreadsheet className="w-4 h-4" /> Excel-отчёт
          </button>
          <button onClick={() => setShowDistricts((v) => !v)} className="btn-outline flex-1 flex items-center justify-center gap-2 text-sm py-2">
            <MapPin className="w-4 h-4" /> По районам
          </button>
        </div>

        {/* District stats */}
        {showDistricts && districts && (
          <div className="card dark:bg-gray-800 dark:border-gray-700 space-y-2">
            <h3 className="font-semibold text-sm text-gray-800 dark:text-gray-100">Охват по районам</h3>
            {districts.map((d) => (
              <div key={d.district_name} className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-gray-600 dark:text-gray-400 truncate flex-1 mr-2">{d.district_name}</span>
                  <span className="text-gray-800 dark:text-gray-200 font-medium">{d.inspected}/{d.total_sites} ({d.percent}%)</span>
                </div>
                <div className="h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                  <div className="h-full bg-green-500 rounded-full transition-all" style={{ width: `${Math.min(d.percent, 100)}%` }} />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function StatCard({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: number; color: string }) {
  return (
    <div className="card dark:bg-gray-800 dark:border-gray-700 p-3 flex items-center gap-3">
      <div className={`w-10 h-10 ${color} rounded-xl flex items-center justify-center text-white shrink-0`}>{icon}</div>
      <div>
        <div className="text-xs text-gray-400 dark:text-gray-500">{label}</div>
        <div className="text-xl font-bold text-gray-800 dark:text-gray-100">{value}</div>
      </div>
    </div>
  )
}
