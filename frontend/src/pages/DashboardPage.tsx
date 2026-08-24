import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { ArrowLeft, Download, FileSpreadsheet, RefreshCw } from 'lucide-react'
import { districtsApi, reportsApi, statsApi } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { notify as toast } from '@/lib/toast'
import { coverageColor, currentMskWeek, percentageColor, periodRange, withTotalsRow, type StatisticsPreset } from '@/lib/statistics'
import type { StatsDistrictRow } from '@/types'

type Tab = 'overview' | 'dynamics' | 'categories' | 'districts' | 'remediation' | 'shtab'
type PeriodMode = StatisticsPreset | 'all' | 'custom'
type DistrictMetricGroup = 'sites' | 'inspections'

const districtMetricGroups: { id: DistrictMetricGroup; label: string; hint: string; className: string }[] = [
  { id: 'sites', label: 'Площадки', hint: 'объекты и охват', className: 'bg-sky-100 text-sky-950' },
  { id: 'inspections', label: 'Обходы', hint: 'результат обходов', className: 'bg-emerald-100 text-emerald-950' },
]

const districtColumns: { key: keyof StatsDistrictRow; label: string; group?: DistrictMetricGroup; groupStart?: boolean }[] = [
  { key: 'district_name', label: 'Район' },
  { key: 'total_sites', label: 'Площадок', group: 'sites', groupStart: true },
  { key: 'sites_inspected', label: 'Проверено', group: 'sites' },
  { key: 'coverage_pct', label: 'Охват %', group: 'sites' },
  { key: 'inspections_total', label: 'Обходов', group: 'inspections', groupStart: true },
  { key: 'inspections_green', label: 'Без нарушений', group: 'inspections' },
  { key: 'inspections_with_defects', label: 'С наруш.', group: 'inspections' },
]

const tabs: [Tab, string][] = [
  ['overview', 'Обзор'], ['dynamics', 'Динамика'], ['categories', 'Категории'],
  ['districts', 'Обходы'], ['remediation', 'Устранение'], ['shtab', 'Штаб-отчёт'],
]

export default function DashboardPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const [defaultFrom, defaultTo] = currentMskWeek()
  const [dateFrom, setDateFrom] = useState(defaultFrom)
  const [dateTo, setDateTo] = useState(defaultTo)
  const [periodMode, setPeriodMode] = useState<PeriodMode>('week')
  const [tab, setTab] = useState<Tab>('overview')
  const lockedDistrict = user?.role === 'reviewer' ? user.district_id : undefined
  const [districtId, setDistrictId] = useState(lockedDistrict || '')
  const params = { date_from: dateFrom, date_to: dateTo, district_id: districtId || undefined, all_time: periodMode === 'all' || undefined }
  const selectPreset = (mode: Exclude<PeriodMode, 'custom'>) => {
    setPeriodMode(mode)
    if (mode !== 'all') {
      const [from, to] = periodRange(mode)
      setDateFrom(from)
      setDateTo(to)
    }
  }
  const updateDateFrom = (value: string) => { setPeriodMode('custom'); setDateFrom(value) }
  const updateDateTo = (value: string) => { setPeriodMode('custom'); setDateTo(value) }
  const refreshStatistics = () => queryClient.invalidateQueries({ queryKey: ['stats-v2'] })

  const { data: districts } = useQuery({ queryKey: ['districts'], queryFn: districtsApi.list })
  const dashboard = useQuery({
    queryKey: ['stats-v2-dashboard', params], queryFn: () => statsApi.dashboard(params),
    refetchInterval: 60_000,
  })
  const dynamics = useQuery({
    queryKey: ['stats-v2-dynamics', params], queryFn: () => statsApi.dynamics(params),
    enabled: tab === 'dynamics',
  })
  const categories = useQuery({
    queryKey: ['stats-v2-categories', params], queryFn: () => statsApi.categories(params),
    enabled: tab === 'categories',
  })
  const generated = dashboard.data?.generated_at
    ? new Date(dashboard.data.generated_at).toLocaleString('ru-RU') : '—'

  const exportXlsx = () => toast.promise(reportsApi.exportXlsx(params), {
    loading: 'Готовлю Excel…', success: 'Excel скачан', error: 'Ошибка выгрузки',
  })

  return <div className="h-full flex flex-col bg-slate-50">
    <header className="bg-primary-800 text-white px-4 py-3 flex items-center gap-3 shrink-0">
      <button onClick={() => navigate(user?.role === 'admin' ? '/admin' : '/')} className="p-2"><ArrowLeft /></button>
      <div className="flex-1"><h1 className="font-bold text-lg">Статистика v2</h1><p className="text-xs text-blue-200">МСК · сформировано {generated}</p></div>
      <button aria-label="Обновить статистику" onClick={refreshStatistics} className="p-2"><RefreshCw className="w-5" /></button>
    </header>

    <section className="bg-white border-b p-3 flex gap-2 flex-wrap">
      {lockedDistrict ? <div className="input-field text-sm !w-64 bg-gray-50">{districts?.find(d => d.id === lockedDistrict)?.name || 'Ваш район'}</div>
        : <select className="input-field text-sm !w-64" value={districtId} onChange={e => setDistrictId(e.target.value)}>
            <option value="">Все районы</option>{districts?.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>}
      <div className="flex rounded-md border overflow-hidden" role="group" aria-label="Период статистики">
        {([['day', 'День'], ['week', 'Неделя'], ['month', 'Месяц'], ['all', 'Все время']] as const).map(([mode, label]) => <button key={mode} onClick={() => selectPreset(mode)} className={`px-3 py-2 text-sm ${periodMode === mode ? 'bg-primary-700 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'}`}>{label}</button>)}
      </div>
      <input aria-label="Дата начала" className="input-field text-sm !w-40" type="date" value={dateFrom} onChange={e => updateDateFrom(e.target.value)} disabled={periodMode === 'all'} />
      <input aria-label="Дата окончания" className="input-field text-sm !w-40" type="date" value={dateTo} onChange={e => updateDateTo(e.target.value)} disabled={periodMode === 'all'} />
      <button className="btn-outline flex gap-2 items-center text-sm" onClick={exportXlsx}><FileSpreadsheet className="w-4" />Excel</button>
    </section>

    <nav className="bg-white px-3 pt-2 flex overflow-x-auto border-b">
      {tabs.map(([id, label]) => <button key={id} onClick={() => setTab(id)} className={`px-4 py-2 text-sm whitespace-nowrap border-b-2 ${tab === id ? 'border-primary-700 text-primary-700 font-semibold' : 'border-transparent text-gray-500'}`}>{label}</button>)}
    </nav>

    <main className="flex-1 overflow-y-auto p-4">
      {dashboard.isLoading ? <State text="Загрузка…" /> : dashboard.isError || !dashboard.data ? <State text="Не удалось загрузить статистику" /> : <>
        {tab === 'overview' && <Overview total={dashboard.data.totals} />}
        {tab === 'dynamics' && (dynamics.data ? <Dynamics data={dynamics.data.days} /> : <State text="Загрузка динамики…" />)}
        {tab === 'categories' && (categories.data ? <Categories data={categories.data.categories} /> : <State text="Загрузка категорий…" />)}
        {tab === 'districts' && <DistrictTable rows={dashboard.data.districts} totals={dashboard.data.totals} onSelect={lockedDistrict ? undefined : setDistrictId} />}
        {tab === 'remediation' && <RemediationTable rows={dashboard.data.districts} totals={dashboard.data.totals} />}
        {tab === 'shtab' && <Shtab params={params} />}
      </>}
    </main>
  </div>
}

function State({ text }: { text: string }) { return <div className="h-60 grid place-items-center text-gray-500">{text}</div> }
function Kpi({ label, value, detail }: { label: string; value: number | string; detail?: string }) {
  return <div className="card"><div className="text-xs text-gray-500">{label}</div><div className="text-2xl font-bold mt-1">{value}</div>{detail && <div className="text-xs text-primary-700 mt-1">{detail}</div>}</div>
}
function Overview({ total: t }: { total: StatsDistrictRow }) {
  const funnel = [
    { name: 'Выявлено', value: t.issues_found }, { name: 'Не устранено', value: t.issues_not_fixed },
    { name: 'В работе', value: t.issues_in_work }, { name: 'На проверке', value: t.issues_on_check },
    { name: 'Устранено', value: t.issues_closed },
  ]
  const coverage = [{ name: 'Проверено', value: t.sites_inspected }, { name: 'Не проверено', value: Math.max(0, t.total_sites - t.sites_inspected) }]
  return <div className="space-y-4">
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <Kpi label="Площадок" value={t.total_sites} /><Kpi label="Охват" value={`${t.coverage_pct}%`} detail={`${t.sites_inspected} из ${t.total_sites} площадок проверено`} />
      <Kpi label="Обходов" value={t.inspections_total} /><Kpi label="Зелёных" value={t.inspections_green} />
      <Kpi label="С нарушениями" value={t.inspections_with_defects} /><Kpi label="Выявлено за период" value={t.issues_found} />
      <Kpi label="На финальной проверке" value={t.issues_fixed_events} /><Kpi label="Исправлено за период" value={t.issues_closed_events} />
      <Kpi label="Возвращено на доработку" value={t.issues_revision_events} /><Kpi label="Просрочено сейчас" value={t.issues_overdue_current} />
    </div>
    <div className="grid lg:grid-cols-2 gap-4">
      <ChartCard title="Статус замечаний, выявленных за период"><ResponsiveContainer width="100%" height={280}><BarChart data={funnel} layout="vertical"><CartesianGrid strokeDasharray="3 3"/><XAxis type="number"/><YAxis dataKey="name" type="category" width={95}/><Tooltip/><Bar dataKey="value" fill="#9E2B25" /></BarChart></ResponsiveContainer></ChartCard>
      <ChartCard title="Охват"><ResponsiveContainer width="100%" height={280}><PieChart><Pie data={coverage} dataKey="value" nameKey="name" innerRadius={65} outerRadius={105} label>{coverage.map((_, i) => <Cell key={i} fill={i ? '#D9D9D9' : '#63BE7B'} />)}</Pie><Tooltip/><Legend/></PieChart></ResponsiveContainer></ChartCard>
    </div>
  </div>
}
function ChartCard({ title, children }: { title: string; children: React.ReactNode }) { return <div className="card"><h2 className="font-semibold mb-3">{title}</h2>{children}</div> }
function Dynamics({ data }: { data: { date: string; inspections: number; issues_found: number; closure_events: number }[] }) {
  return <div className="space-y-4"><ChartCard title="Динамика по дням"><ResponsiveContainer width="100%" height={330}><LineChart data={data}><CartesianGrid strokeDasharray="3 3"/><XAxis dataKey="date"/><YAxis allowDecimals={false}/><Tooltip/><Legend/><Line dataKey="inspections" name="Обходы" stroke="#2563EB"/><Line dataKey="issues_found" name="Выявлено" stroke="#E06666"/><Line dataKey="closure_events" name="Устранено" stroke="#63BE7B"/></LineChart></ResponsiveContainer></ChartCard>
    <div className="card overflow-x-auto"><table className="w-full text-sm"><thead><tr><th>Дата</th><th>Обходы</th><th>Выявлено</th><th>Устранено</th></tr></thead><tbody>{data.map(d => <tr className="border-t text-center" key={d.date}><td className="p-2">{d.date}</td><td>{d.inspections}</td><td>{d.issues_found}</td><td>{d.closure_events}</td></tr>)}</tbody></table></div></div>
}
function Categories({ data }: { data: { category_id: string; name: string; found: number; closed: number; not_fixed: number; overdue: number; closed_pct: number }[] }) {
  const sorted = [...data].sort((a, b) => b.found - a.found)
  return <div className="space-y-4"><ChartCard title="Нарушения по категориям"><ResponsiveContainer width="100%" height={360}><BarChart data={sorted} layout="vertical"><CartesianGrid strokeDasharray="3 3"/><XAxis type="number"/><YAxis dataKey="name" type="category" width={150}/><Tooltip/><Bar dataKey="found" name="Выявлено" fill="#9E2B25"/></BarChart></ResponsiveContainer></ChartCard>
    <div className="card overflow-x-auto"><table className="w-full text-sm"><thead><tr><th>Категория</th><th>Выявлено</th><th>Устранено</th><th>Не устранено</th><th>Просрочено</th><th>%</th></tr></thead><tbody>{data.map(r => <tr className="border-t text-center" key={r.category_id}><td className="p-2 text-left">{r.name}</td><td>{r.found}</td><td>{r.closed}</td><td>{r.not_fixed}</td><td>{r.overdue}</td><td style={{background:percentageColor(r.closed_pct)}}>{r.closed_pct}%</td></tr>)}</tbody></table></div></div>
}
function DistrictTable({ rows, totals, onSelect }: { rows: StatsDistrictRow[]; totals: StatsDistrictRow; onSelect?: (id: string) => void }) {
  const [sort, setSort] = useState<keyof StatsDistrictRow>('district_name')
  const ordered = useMemo(() => [...rows].sort((a,b) => typeof a[sort] === 'number' ? Number(b[sort])-Number(a[sort]) : String(a[sort]).localeCompare(String(b[sort]), 'ru')), [rows, sort])
  return <div className="card overflow-x-auto">
    <p className="mb-3 text-sm text-slate-600">Сводка только по обходам за выбранный период. Район без выявленных нарушений — хороший результат, а не нулевой показатель устранения.</p>
    <table className="w-full min-w-[760px] text-xs border border-slate-300">
      <thead>
        <tr>
          <th rowSpan={2} aria-sort={sort === 'district_name' ? 'ascending' : 'none'} className="border border-slate-300 bg-slate-100 p-0 text-left text-slate-800">
            <button type="button" onClick={() => setSort('district_name')} className="h-full w-full px-3 py-2 text-left font-semibold hover:bg-slate-200 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-primary-700">
              Район
            </button>
          </th>
          {districtMetricGroups.map((group) => (
            <th key={group.id} colSpan={districtColumns.filter((column) => column.group === group.id).length} className={`border border-slate-300 px-2 py-1.5 text-center font-bold ${group.className}`}>
              {group.label}<span className="ml-1 font-normal opacity-70">· {group.hint}</span>
            </th>
          ))}
        </tr>
        <tr>
          {districtColumns.slice(1).map(({ key, label, group, groupStart }) => {
            const groupClass = districtMetricGroups.find((item) => item.id === group)?.className ?? 'bg-slate-100 text-slate-800'
            return <th key={key} aria-sort={sort === key ? 'descending' : 'none'} className={`border border-slate-300 p-0 whitespace-nowrap ${groupClass} ${groupStart ? 'border-l-2 border-l-slate-500' : ''}`}>
              <button type="button" onClick={() => setSort(key)} className="w-full px-2 py-2 text-center font-semibold hover:brightness-95 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-primary-700">
                {label}
              </button>
            </th>
          })}
        </tr>
      </thead>
      <tbody>
        {withTotalsRow(ordered, totals).map((r) => {
          const isTotal = r.district_id === totals.district_id
          return <tr key={r.district_id} onClick={() => !isTotal && onSelect?.(r.district_id)} className={isTotal ? 'border-t text-center bg-slate-700 text-white font-bold' : onSelect ? 'border-t text-center cursor-pointer hover:bg-blue-50' : 'border-t text-center'}>
            {districtColumns.map(({ key, groupStart }) => <td key={key} className={`border border-slate-300 p-2 whitespace-nowrap ${groupStart ? isTotal ? 'border-l-2 border-l-white/50' : 'border-l-2 border-l-slate-400' : ''} ${!isTotal && key === 'inspections_with_defects' && Number(r[key]) === 0 && Number(r.inspections_total) > 0 ? 'bg-emerald-50 text-emerald-800 font-semibold' : ''}`} style={!isTotal && key === 'coverage_pct' ? { background: coverageColor(Number(r[key])) } : undefined}>
              {key === 'district_name' && isTotal ? 'ИТОГО' : key === 'coverage_pct' ? `${r[key]}%` : r[key]}
            </td>)}
          </tr>
        })}
      </tbody>
    </table>
  </div>
}
function RemediationTable({ rows, totals }: { rows: StatsDistrictRow[]; totals: StatsDistrictRow }) {
  const [sort, setSort] = useState<keyof StatsDistrictRow>('district_name')
  const columns: { key: keyof StatsDistrictRow; label: string; group: string }[] = [
    { key: 'issues_found', label: 'Выявлено', group: 'За период' },
    { key: 'issues_fixed_events', label: 'На финальной проверке', group: 'За период' },
    { key: 'issues_closed_events', label: 'Исправлено', group: 'За период' },
    { key: 'issues_revision_events', label: 'Доработка', group: 'За период' },
    { key: 'issues_pending_final_current', label: 'На проверке', group: 'Сейчас' },
    { key: 'issues_requires_work_current', label: 'Требуют работы', group: 'Сейчас' },
    { key: 'issues_overdue_current', label: 'Просрочено', group: 'Сейчас' },
  ]
  const ordered = useMemo(() => [...rows].sort((a, b) => typeof a[sort] === 'number' ? Number(b[sort]) - Number(a[sort]) : String(a[sort]).localeCompare(String(b[sort]), 'ru')), [rows, sort])
  const groups = ['За период', 'Сейчас']
  return <div className="card overflow-x-auto">
    <p className="mb-3 text-sm text-slate-600">«Исправлено» — замечания, принятые окончательно. «На финальной проверке» — материалы переданы и ожидают решения. При отсутствии замечаний показатели не окрашиваются как проблемные.</p>
    <table className="w-full min-w-[980px] text-xs border border-slate-300"><thead><tr>
      <th rowSpan={2} aria-sort={sort === 'district_name' ? 'ascending' : 'none'} className="border border-slate-300 bg-slate-100 p-0 text-left"><button type="button" onClick={() => setSort('district_name')} className="h-full w-full px-2 py-2 text-left font-semibold hover:bg-slate-200 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-primary-700">Район</button></th>
      {groups.map(group => <th key={group} colSpan={columns.filter(c => c.group === group).length} className={`border border-slate-300 p-2 ${group === 'За период' ? 'bg-orange-100 text-orange-950' : 'bg-slate-100 text-slate-800'}`}>{group}</th>)}
    </tr><tr>{columns.map(({ key, label, group }) => <th key={key} className={`border border-slate-300 p-0 ${group === 'За период' ? 'bg-orange-50' : 'bg-slate-50'}`}><button type="button" onClick={() => setSort(key)} className="w-full px-2 py-2 font-semibold hover:bg-slate-100">{label}</button></th>)}</tr></thead>
    <tbody>{withTotalsRow(ordered, totals).map(r => { const total = r.district_id === totals.district_id; return <tr key={r.district_id} className={total ? 'bg-slate-700 text-center font-bold text-white' : 'text-center'}><td className="border border-slate-300 p-2 text-left">{total ? 'ИТОГО' : r.district_name}</td>{columns.map(({ key }) => <td key={key} className={`border border-slate-300 p-2 ${!total && key === 'issues_closed_events' && Number(r[key]) > 0 ? 'bg-emerald-50 text-emerald-800 font-semibold' : ''} ${!total && key === 'issues_overdue_current' && Number(r[key]) > 0 ? 'bg-red-100 text-red-900 font-semibold' : ''}`}>{r[key]}</td>)}</tr>})}</tbody>
    </table>
  </div>
}
function Shtab({ params }: { params: { date_from: string; date_to: string; district_id?: string; all_time?: boolean } }) {
  const preview = useQuery({ queryKey:['shtab-preview', params], queryFn:() => statsApi.dashboard(params) })
  const download = () => toast.promise(statsApi.downloadShtab(params), { loading:'Формирую PPTX…', success:'PPTX скачан', error:'Ошибка выгрузки' })
  return <div className="space-y-4"><div className="card flex flex-wrap items-end gap-3"><p className="text-sm text-gray-600">Используется выбранный выше период: {params.all_time ? 'всё время' : `${params.date_from} — ${params.date_to}`}</p><button onClick={download} className="btn-primary flex items-center gap-2"><Download className="w-4"/>Скачать PPTX</button></div>{preview.data ? <DistrictTable rows={preview.data.districts} totals={preview.data.totals}/> : <State text="Загрузка превью…"/>}</div>
}
