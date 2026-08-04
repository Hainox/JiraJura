import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { notify } from './toast'

// Мокаем react-hot-toast
vi.mock('react-hot-toast', () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
    loading: vi.fn(() => 'loading-id'),
    dismiss: vi.fn(),
    promise: vi.fn(),
  },
}))

describe('notify (deduplicated toast)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('success вызывает toast.success с правильными параметрами', async () => {
    const toastModule = await import('react-hot-toast')
    notify.success('Тестовое сообщение')
    expect(toastModule.default.success).toHaveBeenCalledWith(
      'Тестовое сообщение',
      { duration: 3000 },
    )
  })

  it('error вызывает toast.error с duration 4000', async () => {
    const toastModule = await import('react-hot-toast')
    notify.error('Ошибка')
    expect(toastModule.default.error).toHaveBeenCalledWith(
      'Ошибка',
      { duration: 4000 },
    )
  })

  it('дедуплицирует одинаковые сообщения в течение 2 секунд', async () => {
    const toastModule = await import('react-hot-toast')
    notify.success('Дубль')
    notify.success('Дубль')
    // Первый прошёл, второй — нет (дедупликация)
    expect(toastModule.default.success).toHaveBeenCalledTimes(1)

    // Через 3 секунды — снова можно
    vi.advanceTimersByTime(3000)
    notify.success('Дубль')
    expect(toastModule.default.success).toHaveBeenCalledTimes(2)
  })

  it('разные сообщения не дедуплицируются', async () => {
    const toastModule = await import('react-hot-toast')
    notify.success('Первое')
    notify.success('Второе')
    expect(toastModule.default.success).toHaveBeenCalledTimes(2)
  })

  it('loading проксирует напрямую без дедупликации', async () => {
    const toastModule = await import('react-hot-toast')
    notify.loading('Загрузка...')
    expect(toastModule.default.loading).toHaveBeenCalledWith('Загрузка...')
  })
})
