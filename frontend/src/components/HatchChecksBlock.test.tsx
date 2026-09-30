import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import HatchChecksBlock from './HatchChecksBlock'
import type { InspectionHatchOut } from '@/types'

const { mockForInspection, mockSaveCheck, mockAllOk } = vi.hoisted(() => ({
  mockForInspection: vi.fn(),
  mockSaveCheck: vi.fn(),
  mockAllOk: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  hatchesApi: { forInspection: mockForInspection, saveCheck: mockSaveCheck, markRemainingOk: mockAllOk },
  issuesApi: { uploadPhoto: vi.fn() },
  describeInspectionUpdateError: () => 'ошибка',
  describeUploadError: () => 'ошибка фото',
}))
vi.mock('@/lib/toast', () => ({ notify: { success: vi.fn(), error: vi.fn() } }))

const hatch = (id: string, number: string, owner?: string) => ({
  id, site_id: 'site-1', number, owner, location_note: null, external_id: null,
  is_active: true, lat: null, lon: null, created_at: '2026-09-30T06:00:00Z',
})

const okCheck = {
  id: 'check-2', inspection_id: 'insp-1', hatch_id: 'h2', state: 'ok' as const, fenced: null,
  owner_ticket: null, comment: null, issue_id: null, issue_status: null, issue_due_date: null,
  photos: [], checked_by: 'user-1', checked_by_name: 'Инспектор', created_at: '2026-09-30T07:15:00Z', updated_at: null,
}

const ITEMS: InspectionHatchOut[] = [
  { hatch: hatch('h1', '1', 'Мосводоканал'), check: null },
  { hatch: hatch('h2', '2'), check: okCheck },
]

function renderBlock(editable = true) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <HatchChecksBlock inspectionId="insp-1" editable={editable} />
    </QueryClientProvider>,
  )
}

describe('HatchChecksBlock — люки в обходе', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockForInspection.mockResolvedValue(ITEMS)
  })

  it('выбор дефекта сразу сохраняет осмотр и показывает требования к фото', async () => {
    mockSaveCheck.mockResolvedValue({
      ...okCheck, id: 'check-1', hatch_id: 'h1', state: 'damaged', fenced: false,
      issue_id: 'issue-1', issue_status: 'open', issue_due_date: '2026-10-01',
    })
    renderBlock()

    expect(await screen.findByText('Люки: отмечено 1 из 2')).toBeInTheDocument()
    expect(screen.getByText('не отмечен')).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /Люк №1 · Мосводоканал/ }))
    const states = screen.getByRole('radiogroup', { name: 'Состояние: Люк №1 · Мосводоканал' })
    expect(within(states).getAllByRole('radio')).toHaveLength(5)
    expect(within(states).getByRole('radio', { name: 'Провал / просадка вокруг люка' })).toBeInTheDocument()

    await user.click(within(states).getByRole('radio', { name: 'Крышка повреждена' }))
    expect(mockSaveCheck).toHaveBeenCalledWith('insp-1', 'h1', {
      state: 'damaged', fenced: false, owner_ticket: null, comment: null,
    })

    expect(await screen.findByText('Люки: отмечено 2 из 2')).toBeInTheDocument()
    expect(within(states).getByRole('radio', { name: '✓ Крышка повреждена' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByText(/Создано критическое замечание «Люки» со сроком 1 день \(до 01\.10\.2026\)/)).toBeInTheDocument()
    expect(screen.getByText('— обязательно')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Добавить фото нарушения' })).toBeInTheDocument()
    expect(screen.getByLabelText('Опасное место ограждено')).not.toBeChecked()
    expect(screen.getByLabelText('№ заявки владельцу люка')).toBeInTheDocument()
    // Все люки отмечены — кнопка «Остальные исправны» больше не нужна.
    expect(screen.queryByRole('button', { name: 'Остальные люки исправны' })).not.toBeInTheDocument()
  })

  it('«Остальные люки исправны» отмечает неотмеченные одним нажатием', async () => {
    mockAllOk.mockResolvedValue([{ ...ITEMS[0], check: { ...okCheck, id: 'check-1', hatch_id: 'h1' } }, ITEMS[1]])
    renderBlock()

    await userEvent.setup().click(await screen.findByRole('button', { name: 'Остальные люки исправны' }))
    expect(mockAllOk).toHaveBeenCalledWith('insp-1')
    expect(await screen.findByText('Люки: отмечено 2 из 2')).toBeInTheDocument()
  })

  it('вне своего незавершённого обхода — только просмотр', async () => {
    renderBlock(false)
    await userEvent.setup().click(await screen.findByRole('button', { name: /Люк №1 · Мосводоканал/ }))
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Остальные люки исправны' })).not.toBeInTheDocument()
    expect(screen.getByText('Люк не отмечен в этом обходе.')).toBeInTheDocument()
  })

  it('площадка без люков — блока нет', async () => {
    mockForInspection.mockResolvedValue([])
    const { container } = renderBlock()
    await vi.waitFor(() => expect(mockForInspection).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })
})
