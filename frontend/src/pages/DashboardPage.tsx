import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { reportsApi, districtsApi } from '@/lib/api'
import type { DashboardOut, DistrictOut } from '@/types'
import {
  ArrowLeft, RefreshCw, FileSpreadsheet, Building, ClipboardCheck,
  AlertTriangle, Clock, CheckCircle2, RotateCcw, MapPin,
} from 'lucide-react'
import { notify as toast } from '@/lib/toast'

export default function DashboardPage() {
  const navigate = useNavigate()

  const today = new Date().toISOString().slice(0, 10)
  const weekAgo = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10)

  const [districtFilter, setDistrictFilter] = useState<string>('')
  const [dateFrom, setDateFrom] = useState<string>(weekAgo)
  const [dateTo, setDateTo] = useState<string>(today)

  const { data: districts } = useQuery<DistrictOut[]>({
    queryKey: ['districts'],
    queryFn: districtsApi.list,
  })

  const { data, isLoading, refetch } = useQuery<DashboardOut>({
    queryKey: ['dashboard', districtFilter, dateFrom, dateTo],
    queryFn: () => reportsApi.dashboard({
      district_id: districtFilter || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
    }),
    refetchInterval: 60_000, // автообновление раз в минуту
  })

  const exportXlsx = () => {
    toast.promise(reportsApi.exportXlsx({
      district_id: districtFilter || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
    }), {
      loading: 'Готовлю файл...', success: 'Отчёт скачан', error: 'Ошибка выгрузки',
    })
  }

  const t = data?.totals

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* Header */}
      <div className="bg-primary-800 text-white px-4 py-3 flex items-center gap-3 shrink-0">
        <button onClick={() => navigate('/')} className="p-1.5 rounded-lg hover:bg-primary-700">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex-1">
          <h1 className="text-lg font-bold">Дашборд</h1>
          <p className="text-blue-200 text-xs">Сводка по округу</p>
        </div>
        <button onClick={() => refetch()} className="p-2 rounded-lg hover:bg-primary-700">
          <RefreshCw className="w-5 h-5" />
        </button>
      </div>

      {/* Filters */}
      <div className="bg-white border-b px-4 py-2 shrink-0 flex gap-2 flex-wrap">
        <select
          className="input-field text-sm flex-1 min-w-[140px]"
          value={districtFilter}
          onChange={(e) => setDistrictFilter(e.target.value)}
        >
          <option value="">Все районы</option>
          {districts?.map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
        <input
          type="date"
          className="input-field text-sm w-[130px]"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          title="С даты"
        />
        <input
          type="date"
          className="input-field text-sm w-[130px]"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          title="По дату"
        />
        <button onClick={exportXlsx} className="btn-outline text-sm px-3 py-1.5 flex items-center gap-1 shrink-0">
          <FileSpreadsheet className="w-4 h-4" /> Excel
        </button>
      </div>

      {isLoading ? (
        <div className="flex-1 flex items-center justify-center text-gray-400">Загрузка...</div>
      ) : (
        <div className="overflow-y-auto flex-1 p-4 space-y-4">
          {/* KPI cards — totals */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCard icon={<ClipboardCheck className="w-5 h-5" />} label="Обходов" value={t?.inspections_total ?? 0} color="bg-blue-500" />
            <KpiCard icon={<CheckCircle2 className="w-5 h-5" />} label="Завершено" value={t?.inspections_completed ?? 0} color="bg-green-500" />
            <KpiCard icon={<Clock className="w-5 h-5" />} label="В процессе" value={t?.inspections_in_progress ?? 0} color="bg-yellow-500" />
            <KpiCard icon={<Building className="w-5 h-5" />} label="Площадок" value={t?.total_sites ?? 0} color="bg-indigo-500" />
          </div>

          {/* KPI cards — issues */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <KpiCard icon={<AlertTriangle className="w-5 h-5" />} label="Замечаний" value={t?.issues_total ?? 0} color="bg-red-500" />
            <KpiCard icon={<AlertTriangle className="w-5 h-5" />} label="Открыто" value={t?.issues_open ?? 0} color="bg-orange-500" />
            <KpiCard icon={<CheckCircle2 className="w-5 h-5" />} label="Исправлено" value={t?.issues_fixed ?? 0} color="bg-emerald-500" />
            <KpiCard icon={<RotateCcw className="w-5 h-5" />} label="На доработке" value={t?.issues_revision_needed ?? 0} color="bg-amber-500" />
            <KpiCard icon={<CheckCircle2 className="w-5 h-5" />} label="Принято" value={t?.issues_closed ?? 0} color="bg-green-600" />
          </div>

          {/* Таблица по районам */}
          <div className="card overflow-hidden">
            <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-1.5">
              <MapPin className="w-4 h-4 text-primary-600" />
              По районам
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-gray-500 bg-gray-50">
                    <th className="p-2 font-medium whitespace-nowrap sticky left-0 bg-gray-50">Район</th>
                    <th className="p-2 font-medium text-center">Площадок</th>
                    <th className="p-2 font-medium text-center">Обходов</th>
                    <th className="p-2 font-medium text-center">Заверш.</th>
                    <th className="p-2 font-medium text-center">Замечаний</th>
                    <th className="p-2 font-medium text-center">Открыто</th>
                    <th className="p-2 font-medium text-center">Исправл.</th>
                    <th className="p-2 font-medium text-center">Доработка</th>
                    <th className="p-2 font-medium text-center">Принято</th>
                  </tr>
                </thead>
                <tbody>
                  {/* Totals row */}
                  {t && (
                    <tr className="border-t bg-blue-50 font-semibold text-gray-800">
                      <td className="p-2 sticky left-0 bg-blue-50 whitespace-nowrap">ВСЕГО</td>
                      <td className="p-2 text-center">{t.total_sites}</td>
                      <td className="p-2 text-center">{t.inspections_total}</td>
                      <td className="p-2 text-center">{t.inspections_completed}</td>
                      <td className="p-2 text-center">{t.issues_total}</td>
                      <td className="p-2 text-center">{t.issues_open}</td>
                      <td className="p-2 text-center">{t.issues_fixed}</td>
                      <td className="p-2 text-center">{t.issues_revision_needed}</td>
                      <td className="p-2 text-center">{t.issues_closed}</td>
                    </tr>
                  )}
                  {data?.districts.map((d, i) => (
                    <tr key={d.district_id} className={`border-t ${i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}`}>
                      <td className="p-2 sticky left-0 bg-inherit whitespace-nowrap text-gray-700">{d.district_name}</td>
                      <td className="p-2 text-center text-gray-600">{d.total_sites}</td>
                      <td className="p-2 text-center">{d.inspections_total || '-'}</td>
                      <td className="p-2 text-center text-green-700">{d.inspections_completed || '-'}</td>
                      <td className="p-2 text-center font-medium">{d.issues_total || '-'}</td>
                      <td className="p-2 text-center text-red-600">{d.issues_open || '-'}</td>
                      <td className="p-2 text-center text-emerald-600">{d.issues_fixed || '-'}</td>
                      <td className="p-2 text-center">
                        {d.issues_revision_needed > 0 ? (
                          <span className="bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded-full font-medium">{d.issues_revision_needed}</span>
                        ) : '-'}
                      </td>
                      <td className="p-2 text-center text-green-700">{d.issues_closed || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data?.districts.length === 0 && (
              <div className="text-center text-gray-400 py-8">Нет данных за выбранный период</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function KpiCard({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: number; color: string }) {
  return (
    <div className="card p-3 flex items-center gap-3">
      <div className={`w-10 h-10 ${color} rounded-xl flex items-center justify-center text-white shrink-0`}>
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-xs text-gray-400 truncate">{label}</div>
        <div className="text-xl font-bold text-gray-800">{value}</div>
      </div>
    </div>
  )
}
