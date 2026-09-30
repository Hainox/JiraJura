import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import IssuesPage from './IssuesPage'
import { useIssuesViewStore } from '@/stores/issuesView'

const mocks = vi.hoisted(() => ({ navigate: vi.fn(), list: vi.fn() }))

vi.mock('react-router-dom', async () => ({
  ...(await vi.importActual<object>('react-router-dom')),
  useNavigate: () => mocks.navigate,
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: (selector: (state: unknown) => unknown) => selector({ user: { id: 'u1', role: 'reviewer', district_id: 'd1' } }),
}))

vi.mock('@/lib/api', () => ({
  issuesApi: { list: mocks.list, update: vi.fn() },
  districtsApi: { list: vi.fn(async () => []) },
  authApi: { listUsers: vi.fn(async () => []) },
}))

vi.mock('@/lib/toast', () => ({ notify: { success: vi.fn(), error: vi.fn() } }))

const returnedIssue = {
  id: 'issue-1', title: 'Сломанная доска', criticality: 'medium', status: 'revision_needed',
  site_id: 's1', inspection_id: 'i1', created_by: 'u2', is_overdue: false, created_at: '2026-09-29T00:00:00Z',
}

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><IssuesPage /></MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('IssuesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useIssuesViewStore.getState().reset()
    mocks.list.mockResolvedValue({ total: 1, items: [returnedIssue] })
  })

  it('фильтр статуса умеет отбирать возвращённые на доработку', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Статус' }), 'На доработке')

    await vi.waitFor(() => {
      expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'revision_needed' }))
    })
  })

  it('карточка замечания открывается подписанной кнопкой «Открыть»', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'Открыть' }))
    expect(mocks.navigate).toHaveBeenCalledWith('/issues/issue-1')
  })
})
