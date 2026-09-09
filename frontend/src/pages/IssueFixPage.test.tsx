import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import IssueFixPage from './IssueFixPage'

const { mockUpdate } = vi.hoisted(() => ({ mockUpdate: vi.fn() }))

vi.mock('@/stores/auth', () => ({
  useAuthStore: (selector: (state: { user: { role: string } }) => unknown) => selector({ user: { role: 'reviewer' } }),
}))

vi.mock('@/lib/api', () => ({
  issuesApi: {
    get: vi.fn().mockResolvedValue({
      id: 'issue-1', title: 'Сломанная доска', criticality: 'medium', status: 'revision_needed',
      site_id: 'site-1', inspection_id: 'inspection-1', created_by: 'user-1', is_overdue: false,
      reviewer_comment: 'Покажите результат ремонта крупным планом.', executor_name: '',
      fix_photos: [{ id: 'fix-1', url: '/fix.jpg' }], photos: [{ id: 'before-1', url: '/before.jpg' }],
      created_at: '2026-09-09T00:00:00Z',
    }),
    update: mockUpdate,
    uploadFixPhoto: vi.fn(),
    list: vi.fn(),
  },
  inspectionsApi: { get: vi.fn().mockResolvedValue({ photos: [] }) },
}))

vi.mock('@/lib/usePhotoUpload', () => ({ usePhotoUpload: () => ({ isUploading: false, handleFileInput: vi.fn() }) }))
vi.mock('@/components/BeforeAfterCompare', () => ({ default: () => <div>Сравнение фотографий</div> }))
vi.mock('@/components/PhotoLightbox', () => ({ default: () => null }))
vi.mock('@/stores/demoMode', () => ({ guardDemoAction: (action: () => void) => action() }))
vi.mock('@/lib/toast', () => ({ notify: { success: vi.fn(), error: vi.fn() } }))

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={['/issues/issue-1']}>
        <Routes><Route path="/issues/:id" element={<IssueFixPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('IssueFixPage — повторная отправка', () => {
  beforeEach(() => { vi.clearAllMocks(); mockUpdate.mockResolvedValue({ status: 'fixed' }) })

  it('показывает шаги и отправляет только после указания исполнителя', async () => {
    renderPage()
    expect(await screen.findByText('Карточка возвращена на доработку')).toBeInTheDocument()
    expect(screen.getByText('2. Фото после исправления')).toBeInTheDocument()
    const submit = screen.getByRole('button', { name: 'Отправить на повторную проверку' })
    expect(submit).toBeDisabled()

    await userEvent.setup().type(screen.getByPlaceholderText('Исполнитель работ *'), 'ООО Ремонт')
    expect(submit).toBeEnabled()
    await userEvent.setup().click(submit)

    expect(mockUpdate).toHaveBeenCalledWith('issue-1', expect.objectContaining({
      status: 'fixed', executor_name: 'ООО Ремонт',
    }))
  })
})
