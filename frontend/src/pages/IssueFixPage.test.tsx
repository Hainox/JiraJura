import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import IssueFixPage from './IssueFixPage'
import { acceptableFixPhotos } from '@/lib/issueFix'

const { mockUpdate, mockGet } = vi.hoisted(() => ({ mockUpdate: vi.fn(), mockGet: vi.fn() }))

vi.mock('@/stores/auth', () => ({
  useAuthStore: (selector: (state: { user: { role: string } }) => unknown) => selector({ user: { role: 'reviewer' } }),
}))

vi.mock('@/lib/api', () => ({
  issuesApi: {
    get: mockGet,
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

// Карточку вернули на доработку 29.09 в 10:00 UTC (updated_at проставляет
// тот же PUT, что переводит в revision_needed).
const RETURNED_AT = '2026-09-29T10:00:00Z'
const photoBefore = { id: 'fix-old', url: '/fix-old.jpg', target_type: 'issue_fix', created_at: '2026-09-28T15:00:00Z' }
const photoAfter = { id: 'fix-new', url: '/fix-new.jpg', target_type: 'issue_fix', created_at: '2026-09-29T12:30:00Z' }

function returnedIssue(overrides: Record<string, unknown> = {}) {
  return {
    id: 'issue-1', title: 'Сломанная доска', criticality: 'medium', status: 'revision_needed',
    site_id: 'site-1', inspection_id: 'inspection-1', created_by: 'user-1', is_overdue: false,
    reviewer_comment: 'Покажите результат ремонта крупным планом.', executor_name: '',
    fix_photos: [photoBefore], photos: [{ id: 'before-1', url: '/before.jpg' }],
    created_at: '2026-09-09T00:00:00Z', updated_at: RETURNED_AT,
    ...overrides,
  }
}

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
  beforeEach(() => {
    vi.clearAllMocks()
    mockUpdate.mockResolvedValue({ status: 'fixed' })
  })

  it('показывает шаги и отправляет только после нового фото и указания исполнителя', async () => {
    mockGet.mockResolvedValue(returnedIssue({ fix_photos: [photoBefore, photoAfter] }))
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

  it('фото, загруженное до возврата, не делает карточку готовой — как и на сервере', async () => {
    mockGet.mockResolvedValue(returnedIssue({ executor_name: 'ООО Ремонт' }))
    renderPage()
    await screen.findByText('Карточка возвращена на доработку')

    expect(screen.getByText('Новое фото результата ещё не добавлено')).toBeInTheDocument()
    expect(screen.getByText(/Фото, загруженное до возврата на доработку, не засчитывается/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Загрузить новое фото после исправления/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Отправить на повторную проверку' })).toBeDisabled()
  })

  it('подставляет исполнителя из карточки — повторно вводить не нужно', async () => {
    mockGet.mockResolvedValue(returnedIssue({ executor_name: 'ГБУ Жилищник', fix_photos: [photoAfter] }))
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Карточка возвращена на доработку')

    const executor = screen.getByRole('textbox', { name: 'Исполнитель работ' })
    expect(executor).toHaveValue('ГБУ Жилищник')
    expect(screen.getByText('Новое фото результата добавлено')).toBeInTheDocument()
    const submit = screen.getByRole('button', { name: 'Отправить на повторную проверку' })
    expect(submit).toBeEnabled()

    await user.click(submit)
    expect(mockUpdate).toHaveBeenCalledWith('issue-1', expect.objectContaining({ executor_name: 'ГБУ Жилищник' }))
  })

  it('исполнителя из карточки можно стереть и заменить', async () => {
    mockGet.mockResolvedValue(returnedIssue({ executor_name: 'ГБУ Жилищник', fix_photos: [photoAfter] }))
    const user = userEvent.setup()
    renderPage()
    const executor = await screen.findByRole('textbox', { name: 'Исполнитель работ' })

    await user.clear(executor)
    expect(executor).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Отправить на повторную проверку' })).toBeDisabled()
    await user.type(executor, 'ИП Смирнов')
    expect(executor).toHaveValue('ИП Смирнов')
  })

  it('решение по карточке принимает администратор округа, а не проверяющий', async () => {
    mockGet.mockResolvedValue(returnedIssue())
    renderPage()
    await screen.findByText('Карточка возвращена на доработку')

    expect(screen.getByText(/Это фото увидит администратор округа\./)).toBeInTheDocument()
    expect(screen.getByText('После отправки карточка снова попадёт на проверку администратору округа.')).toBeInTheDocument()
    expect(screen.queryByText(/проверяющ/i)).not.toBeInTheDocument()
  })
})

describe('IssueFixPage — первое исправление', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUpdate.mockResolvedValue({ status: 'fixed' })
  })

  it('любое фото исправления засчитывается, пока карточку не возвращали', async () => {
    mockGet.mockResolvedValue(returnedIssue({
      status: 'open', reviewer_comment: undefined, executor_name: 'ГБУ Жилищник', fix_photos: [photoBefore],
    }))
    renderPage()
    const submit = await screen.findByRole('button', { name: 'Зафиксировать исправление' })
    expect(submit).toBeEnabled()
  })
})

describe('acceptableFixPhotos', () => {
  it('после возврата засчитывает только фото не раньше возврата', () => {
    const issue = { status: 'revision_needed', updated_at: RETURNED_AT, fix_photos: [photoBefore, photoAfter] }
    expect(acceptableFixPhotos(issue).map((p) => p.id)).toEqual(['fix-new'])
  })

  it('разный формат времени (Z и +00:00, микросекунды) сравнивается как время, а не как строка', () => {
    const issue = {
      status: 'revision_needed',
      updated_at: '2026-09-29T10:00:00.123456+00:00',
      fix_photos: [{ ...photoAfter, created_at: '2026-09-29T10:00:01Z' }, { ...photoBefore, created_at: '2026-09-29T09:59:59.999Z' }],
    }
    expect(acceptableFixPhotos(issue).map((p) => p.id)).toEqual(['fix-new'])
  })

  it('без updated_at не блокирует отправку — решение за сервером', () => {
    const issue = { status: 'revision_needed', updated_at: undefined, fix_photos: [photoBefore] }
    expect(acceptableFixPhotos(issue)).toHaveLength(1)
  })
})
