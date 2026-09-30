import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { ArrowLeft, FileSpreadsheet } from 'lucide-react'
import { districtsApi, hatchesApi } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { notify as toast } from '@/lib/toast'
import { currentMskWeek, periodRange, type StatisticsPreset } from '@/lib/statistics'
import {
  HATCH_FIX_LABELS, HATCH_FIX_PILL, HATCH_STATES, HATCH_STATE_PILL, HATCH_STATE_SHORT, mskDateTime, ruDate,
} from '@/lib/hatches'
import type { HatchJournalRow } from '@/types'

const PAGE_SIZE = 50
type PeriodMode = StatisticsPreset | 'custom'

const STATE_OPTIONS: [string, string][] = [
  ['', 'Все состояния'],
  ['defects', 'Только нарушения'],
  ...HATCH_STATES.map((s) => [s, HATCH_STATE_SHORT[s]] as [string, string]),
]

function fixText(row: HatchJournalRow): string {
  if (row.fix_state === 'accepted') return row.closed_at ? `Принято ${mskDateTime(row.closed_at).slice(0, 10)}` : 'Принято'
  if (row.fix_state === 'none') return '—'
  const due = row.due_date ? `, срок ${ruDate(row.due_date)}` : ''
  return `${HATCH_FIX_LABELS[row.fix_state]}${row.fix_state === 'on_check' ? '' : due}`
}

export default function HatchJournalPage() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const isAdmin = user?.role === 'admin'
  const [defaultFrom, defaultTo] = currentMskWeek()
  const [dateFrom, setDateFrom] = useState(defaultFrom)
  const [dateTo, setDateTo] = useState(defaultTo)
  const [periodMode, setPeriodMode] = useState<PeriodMode>('week')
  // Проверяющий района видит только свой район — как на DashboardPage;
  // сервер всё равно закрепляет его за районом, это только интерфейс.
  const lockedDistrict = user?.role === 'reviewer' ? user.district_id : undefined
  const [districtId, setDistrictId] = useState(lockedDistrict || '')
  const [section, setSection] = useState('')
  const [state, setState] = useState('')

  const filters = {
    district_id: districtId || undefined,
    section: section || undefined,
    date_from: dateFrom,
    date_to: dateTo,
    state: state || undefined,
  }

  const { data: districts } = useQuery({ queryKey: ['districts'], queryFn: districtsApi.list })
  const journal = useInfiniteQuery({
    queryKey: ['hatch-journal', filters],
    queryFn: ({ pageParam }) => hatchesApi.journal({ ...filters, page: pageParam, page_size: PAGE_SIZE }),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.page * last.page_size < last.total ? last.page + 1 : undefined),
  })
  const first = journal.data?.pages[0]
  const rows = journal.data?.pages.flatMap((p) => p.rows) ?? []

  const selectPreset = (mode: StatisticsPreset) => {
    const [from, to] = periodRange(mode)
    setPeriodMode(mode)
    setDateFrom(from)
    setDateTo(to)
  }
  const changeDistrict = (value: string) => { setDistrictId(value); setSection('') }
  const issuePath = (issueId: string) => (isAdmin ? `/admin/issues/${issueId}` : `/issues/${issueId}`)

  const exportXlsx = () => toast.promise(hatchesApi.exportJournalXlsx(filters), {
    loading: 'Готовлю Excel…', success: 'Excel скачан', error: 'Ошибка выгрузки',
  })

  return (
    <div className="h-full flex flex-col bg-slate-50">
      <header className="bg-primary-800 text-white px-4 py-3 flex items-center gap-3 shrink-0">
        <button onClick={() => navigate(isAdmin ? '/admin' : '/dashboard')} className="p-2 -ml-2" aria-label="Назад">
          <ArrowLeft />
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="font-bold text-lg">Журнал осмотра люков</h1>
          <p className="text-xs text-blue-200">
            МСК (UTC+3){first ? ` · сформировано ${new Date(first.generated_at).toLocaleString('ru-RU')}` : ''}
          </p>
        </div>
      </header>

      <section className="bg-white border-b p-3 flex gap-2 flex-wrap items-center">
        {lockedDistrict
          ? <div className="input-field text-sm !w-56 bg-gray-50">{districts?.find((d) => d.id === lockedDistrict)?.name || 'Ваш район'}</div>
          : (
            <select aria-label="Район" className="input-field text-sm !w-56" value={districtId} onChange={(e) => changeDistrict(e.target.value)}>
              <option value="">Все районы</option>
              {districts?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          )}
        {districtId && (
          <select aria-label="Участок" className="input-field text-sm !w-44" value={section} onChange={(e) => setSection(e.target.value)}>
            <option value="">Все участки</option>
            {first?.sections.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        )}
        <div className="flex rounded-md border overflow-hidden" role="group" aria-label="Период">
          {([['day', 'День'], ['week', 'Неделя'], ['month', 'Месяц']] as const).map(([mode, label]) => (
            <button
              key={mode}
              onClick={() => selectPreset(mode)}
              className={`px-3 py-2 text-sm ${periodMode === mode ? 'bg-primary-700 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'}`}
            >
              {label}
            </button>
          ))}
        </div>
        <input aria-label="Дата начала" className="input-field text-sm !w-40" type="date" value={dateFrom} onChange={(e) => { setPeriodMode('custom'); setDateFrom(e.target.value) }} />
        <input aria-label="Дата окончания" className="input-field text-sm !w-40" type="date" value={dateTo} onChange={(e) => { setPeriodMode('custom'); setDateTo(e.target.value) }} />
        <select aria-label="Состояние" className="input-field text-sm !w-48" value={state} onChange={(e) => setState(e.target.value)}>
          {STATE_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <button className="btn-outline flex gap-2 items-center text-sm" onClick={exportXlsx}>
          <FileSpreadsheet className="w-4" />Выгрузить в Excel
        </button>
      </section>

      <main className="flex-1 overflow-y-auto p-4 space-y-4">
        {journal.isLoading ? <State text="Загрузка…" />
          : journal.isError || !first ? <State text="Не удалось загрузить журнал" />
          : (
            <>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <Kpi label="Осмотрено сегодня" value={`${first.kpis.checked_today} из ${first.kpis.total_active_hatches}`} />
                <Kpi label="Выявлено нарушений" value={first.kpis.defects_in_period} hint="за период" />
                <Kpi label="Не устранено" value={first.kpis.not_fixed} hint="на сейчас" />
                <Kpi label="Просрочено" value={first.kpis.overdue} hint="на сейчас" alert={first.kpis.overdue > 0} />
              </div>

              {rows.length === 0 ? (
                <div className="card text-center text-gray-500 py-10">
                  {first.kpis.total_active_hatches === 0
                    ? 'Люки на площадках пока не заведены — перечень загрузит округ.'
                    : 'За выбранный период осмотров нет.'}
                </div>
              ) : (
                <div className="card">
                  <div className="sm:hidden space-y-3">
                    {rows.map((r) => <JournalCard key={r.check_id} r={r} onIssue={(id) => navigate(issuePath(id))} />)}
                  </div>
                  <div className="hidden sm:block overflow-x-auto">
                    <table className="w-full min-w-[1100px] text-xs border border-slate-300">
                      <thead>
                        <tr className="bg-slate-100 text-slate-800">
                          {['№', 'Дата, время', 'Район', 'Адрес площадки', 'Тип', 'Люк / владелец', 'Состояние', 'Фото', 'Принятые меры', 'Осмотрел', 'Устранено']
                            .map((h) => <th key={h} className="border border-slate-300 px-2 py-2 font-semibold">{h}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((r) => (
                          <tr key={r.check_id} className="border-t align-top">
                            <td className="border border-slate-300 p-2 text-center">{r.n}</td>
                            <td className="border border-slate-300 p-2 whitespace-nowrap">{mskDateTime(r.created_at)}</td>
                            <td className="border border-slate-300 p-2">{r.district_name}</td>
                            <td className="border border-slate-300 p-2">
                              <button type="button" className="text-left text-primary-700 hover:underline" onClick={() => navigate(`/inspections/${r.inspection_id}`)}>
                                {r.site_address}
                              </button>
                              {r.section && <div className="text-slate-400">{r.section}</div>}
                            </td>
                            <td className="border border-slate-300 p-2">{r.site_type}</td>
                            <td className="border border-slate-300 p-2">
                              №{r.hatch_number}{r.hatch_owner && ` · ${r.hatch_owner}`}
                              {r.location_note && <div className="text-slate-400">{r.location_note}</div>}
                            </td>
                            <td className="border border-slate-300 p-2"><span className={`badge ${HATCH_STATE_PILL[r.state]}`}>{HATCH_STATE_SHORT[r.state]}</span></td>
                            <td className="border border-slate-300 p-2 text-center">{r.state === 'ok' ? '—' : r.has_photo ? 'есть' : <span className="text-red-700">нет</span>}</td>
                            <td className="border border-slate-300 p-2">{r.measures || '—'}</td>
                            <td className="border border-slate-300 p-2">{r.checked_by_name ?? ''}</td>
                            <td className="border border-slate-300 p-2">
                              <FixCell r={r} onIssue={(id) => navigate(issuePath(id))} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="mt-3 flex items-center justify-between gap-3 text-sm text-slate-500">
                    <span>Показано {rows.length} из {first.total}</span>
                    {journal.hasNextPage && (
                      <button className="btn-outline text-sm px-4" onClick={() => journal.fetchNextPage()} disabled={journal.isFetchingNextPage}>
                        {journal.isFetchingNextPage ? 'Загрузка…' : 'Показать ещё'}
                      </button>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
      </main>
    </div>
  )
}

function State({ text }: { text: string }) {
  return <div className="h-60 grid place-items-center text-gray-500">{text}</div>
}

function Kpi({ label, value, hint, alert }: { label: string; value: number | string; hint?: string; alert?: boolean }) {
  return (
    <div className={`card ${alert ? 'border-red-300 bg-red-50' : ''}`}>
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-2xl font-bold mt-1 ${alert ? 'text-red-700' : ''}`}>{value}</div>
      {hint && <div className="text-xs text-gray-400 mt-0.5">{hint}</div>}
    </div>
  )
}

function FixCell({ r, onIssue }: { r: HatchJournalRow; onIssue: (id: string) => void }) {
  if (r.fix_state === 'none' || !r.issue_id) return <span className="text-gray-400">—</span>
  return (
    <button type="button" onClick={() => onIssue(r.issue_id!)} className={`badge text-left ${HATCH_FIX_PILL[r.fix_state]}`}>
      {fixText(r)}
    </button>
  )
}

// Мобильная карточка вместо широкой таблицы — тот же приём, что DistrictCard
// на DashboardPage: 11 колонок журнала на телефоне в строку не помещаются.
function JournalCard({ r, onIssue }: { r: HatchJournalRow; onIssue: (id: string) => void }) {
  return (
    <div className={`rounded-xl border p-3 ${r.state === 'ok' ? 'border-slate-200' : 'border-red-200'}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs text-slate-400">№{r.n} · {mskDateTime(r.created_at)}</div>
          <div className="text-sm font-semibold text-slate-800">{r.site_address}</div>
          <div className="text-xs text-slate-500">{r.district_name}{r.section ? ` · ${r.section}` : ''} · {r.site_type}</div>
        </div>
        <span className={`badge text-xs shrink-0 ${HATCH_STATE_PILL[r.state]}`}>{HATCH_STATE_SHORT[r.state]}</span>
      </div>
      <div className="text-sm text-slate-700 mt-1.5">Люк №{r.hatch_number}{r.hatch_owner && ` · ${r.hatch_owner}`}</div>
      {r.state !== 'ok' && (
        <div className="text-xs text-slate-600 mt-1">
          Фото: {r.has_photo ? 'есть' : <span className="text-red-700">нет</span>}
          {r.measures && <> · {r.measures}</>}
        </div>
      )}
      <div className="flex items-center justify-between gap-2 mt-2">
        <span className="text-xs text-slate-400">{r.checked_by_name ?? ''}</span>
        <FixCell r={r} onIssue={onIssue} />
      </div>
    </div>
  )
}
