import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import HatchJournalPage from './HatchJournalPage'
import type { HatchJournalOut, HatchJournalRow } from '@/types'

const { mockJournal, mockNavigate } = vi.hoisted(() => ({ mockJournal: vi.fn(), mockNavigate: vi.fn() }))

vi.mock('@/stores/auth', () => ({
  useAuthStore: (selector: (state: { user: { role: string; district_id: string } }) => unknown) =>
    selector({ user: { role: 'reviewer', district_id: 'district-1' } }),
}))
vi.mock('react-router-dom', async () => ({
  ...(await vi.importActual<typeof import('react-router-dom')>('react-router-dom')),
  useNavigate: () => mockNavigate,
}))
vi.mock('@/lib/api', () => ({
  hatchesApi: { journal: mockJournal, exportJournalXlsx: vi.fn() },
  districtsApi: { list: vi.fn().mockResolvedValue([{ id: 'district-1', name: 'Коптево' }]) },
}))
vi.mock('@/lib/toast', () => ({ notify: { success: vi.fn(), error: vi.fn(), promise: vi.fn() } }))

const row = (overrides: Partial<HatchJournalRow>): HatchJournalRow => ({
  n: 1, check_id: 'c1', inspection_id: 'i1', created_at: '2026-09-30T06:40:00Z',
  district_name: 'Коптево', section: 'Участок 1', site_id: 's1', site_address: 'Михалковская ул. 20',
  site_type: 'Детская площадка', hatch_id: 'h1', hatch_number: '2', hatch_owner: 'Мосводоканал',
  location_note: null, state: 'damaged', has_photo: true, fenced: true, owner_ticket: '77', comment: null,
  measures: 'ограждено; заявка № 77', checked_by_name: 'Иванов И.И.', issue_id: 'issue-1',
  issue_status: 'open', due_date: '2026-09-29', closed_at: null, fix_state: 'overdue',
  ...overrides,
})

const page = (rows: HatchJournalRow[], extra: Partial<HatchJournalOut> = {}): HatchJournalOut => ({
  period: { date_from: '2026-09-28', date_to: '2026-09-30' }, timezone: 'Europe/Moscow',
  generated_at: '2026-09-30T08:00:00Z',
  kpis: { checked_today: 3, total_active_hatches: 4, defects_in_period: 2, not_fixed: 1, overdue: 1 },
  sections: ['Участок 1', 'Участок 2'], total: 2, page: 1, page_size: 50, rows,
  ...extra,
})

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><HatchJournalPage /></MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('HatchJournalPage — журнал осмотра люков', () => {
  beforeEach(() => { vi.clearAllMocks(); mockJournal.mockReset() })

  it('показывает KPI и строки журнала, район проверяющего закреплён', async () => {
    mockJournal.mockResolvedValueOnce(page([
      row({}),
      row({
        n: 2, check_id: 'c2', hatch_number: '1', hatch_owner: null, state: 'ok', has_photo: false,
        measures: '', issue_id: null, issue_status: null, due_date: null, fix_state: 'none',
      }),
    ], { total: 3, page_size: 2 }))
    mockJournal.mockResolvedValueOnce(page([
      row({ n: 3, check_id: 'c3', hatch_number: '5', state: 'missing', fix_state: 'accepted', closed_at: '2026-09-30T10:00:00Z' }),
    ], { total: 3, page: 2, page_size: 2 }))
    renderPage()

    expect(await screen.findByText('3 из 4')).toBeInTheDocument()
    expect(screen.getByText('Осмотрено сегодня')).toBeInTheDocument()
    expect(screen.getByText('Выявлено нарушений')).toBeInTheDocument()
    expect(screen.getByText('Не устранено')).toBeInTheDocument()
    expect(screen.getByText('Просрочено')).toBeInTheDocument()
    expect(mockJournal).toHaveBeenCalledWith(expect.objectContaining({ district_id: 'district-1', page: 1 }))
    expect(await screen.findByText('Коптево', { selector: 'div' })).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Район' })).not.toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Участок' })).toBeInTheDocument()

    expect(screen.getByRole('columnheader', { name: 'Люк / владелец' })).toBeInTheDocument()
    expect(screen.getAllByText('Михалковская ул. 20').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Крышка повреждена').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Просрочено, срок 29.09.2026').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Исправен').length).toBeGreaterThan(0)
    expect(screen.getByText('Показано 2 из 3')).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Показать ещё' }))
    expect(mockJournal).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }))
    expect(await screen.findByText('Показано 3 из 3')).toBeInTheDocument()
    expect(screen.getAllByText('Принято 30.09.2026').length).toBeGreaterThan(0)

    await user.click(screen.getAllByRole('button', { name: 'Просрочено, срок 29.09.2026' })[0])
    expect(mockNavigate).toHaveBeenCalledWith('/issues/issue-1')
  })

  it('без заведённых люков объясняет, почему журнал пуст', async () => {
    mockJournal.mockResolvedValue(page([], {
      total: 0, kpis: { checked_today: 0, total_active_hatches: 0, defects_in_period: 0, not_fixed: 0, overdue: 0 },
    }))
    renderPage()
    expect(await screen.findByText('Люки на площадках пока не заведены — перечень загрузит округ.')).toBeInTheDocument()
  })
})
