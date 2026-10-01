import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import FeedbackFormPage from './FeedbackFormPage'

vi.mock('@/lib/api', () => ({
  feedbackApi: {
    submit: vi.fn(),
    uploadAttachment: vi.fn(),
  },
}))

vi.mock('@/lib/toast', () => ({
  notify: {
    success: vi.fn(),
    error: vi.fn(),
    loading: vi.fn(),
    dismiss: vi.fn(),
    promise: vi.fn(),
  },
}))

function renderForm(url = '/feedback') {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <FeedbackFormPage />
    </MemoryRouter>,
  )
}

describe('FeedbackFormPage attachments', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('принимает и загружает больше пяти файлов', async () => {
    const { feedbackApi } = await import('@/lib/api')
    vi.mocked(feedbackApi.submit).mockResolvedValue({ id: 'report-1' } as never)
    vi.mocked(feedbackApi.uploadAttachment).mockResolvedValue({ id: 'attachment-1' } as never)

    renderForm()
    const user = userEvent.setup()
    const files = Array.from({ length: 6 }, (_, i) => (
      new File([`image-${i}`], `screenshot-${i}.png`, { type: 'image/png' })
    ))

    await user.upload(screen.getByLabelText('Прикрепить файлы'), files)

    for (const file of files) {
      expect(screen.getByText(file.name)).toBeInTheDocument()
    }
    expect(screen.getByText(/Количество не ограничено/)).toBeInTheDocument()

    await user.type(screen.getByLabelText('Что случилось *'), 'Не работает форма обратной связи')
    await user.click(screen.getByRole('button', { name: 'Отправить' }))

    await vi.waitFor(() => {
      expect(feedbackApi.uploadAttachment).toHaveBeenCalledTimes(6)
    })
    expect(screen.getByText('Обращение принято')).toBeInTheDocument()
  })
})

describe('FeedbackFormPage — обращение из «Люков САО»', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('обычная форма не предлагает жителям тип «Люки САО»', () => {
    renderForm()
    expect(screen.getByText('Журнал обхода площадок САО')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Площадка/двор' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Люки САО' })).not.toBeInTheDocument()
  })

  it('по ссылке ?app=luki отправляет обращение с типом luki и ведёт обратно в «Люки САО»', async () => {
    const { feedbackApi } = await import('@/lib/api')
    vi.mocked(feedbackApi.submit).mockResolvedValue({ id: 'report-1' } as never)

    renderForm('/feedback?app=luki')
    const user = userEvent.setup()

    expect(screen.getByText('Люки САО')).toBeInTheDocument()
    expect(screen.queryByText('Тип обращения')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Площадка/двор' })).not.toBeInTheDocument()

    await user.type(screen.getByLabelText('Где возникло (страница / номер карточки)'), 'ОЛХ-012')
    await user.type(screen.getByLabelText('Что случилось *'), 'Не загружается фото ПОСЛЕ')
    await user.click(screen.getByRole('button', { name: 'Отправить' }))

    await vi.waitFor(() => {
      expect(feedbackApi.submit).toHaveBeenCalledWith(expect.objectContaining({
        report_type: 'luki',
        location_text: 'ОЛХ-012',
        message: 'Не загружается фото ПОСЛЕ',
      }))
    })
    expect(screen.getByRole('link', { name: 'Вернуться в «Люки САО»' })).toHaveAttribute('href', 'https://luki.obhod-sao.ru')
  })
})
