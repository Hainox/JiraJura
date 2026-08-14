import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

describe('FeedbackFormPage attachments', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('принимает и загружает больше пяти файлов', async () => {
    const { feedbackApi } = await import('@/lib/api')
    vi.mocked(feedbackApi.submit).mockResolvedValue({ id: 'report-1' } as never)
    vi.mocked(feedbackApi.uploadAttachment).mockResolvedValue({ id: 'attachment-1' } as never)

    render(<FeedbackFormPage />)
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
