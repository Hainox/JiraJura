import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { usePhotoUpload } from './usePhotoUpload'

// Регрессия: реальное обращение пользователя (iPhone, фото исправления
// нарушения) — file.type для HEIC/HEIF на мобильном Safari/PWA нередко
// пустая строка, а не 'image/heic'. Старая проверка (`!file.type.startsWith
// ('image/')`) отклоняла такие файлы с сообщением "можно загружать только
// изображения", хотя backend их принимает по расширению без вопросов.

vi.mock('@/lib/toast', () => ({
  notify: { success: vi.fn(), error: vi.fn() },
}))
vi.mock('@/lib/api', () => ({
  describeUploadError: () => 'Ошибка загрузки',
}))

function makeFile(name: string, type: string, sizeBytes = 1024): File {
  const file = new File([new Uint8Array(sizeBytes)], name, { type })
  return file
}

describe('usePhotoUpload — валидация файла перед загрузкой', () => {
  let toastError: ReturnType<typeof vi.fn>

  beforeEach(async () => {
    const { notify } = await import('@/lib/toast')
    toastError = notify.error as ReturnType<typeof vi.fn>
    toastError.mockClear()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('принимает HEIC-фото с пустым file.type (реальный кейс с iPhone)', async () => {
    const onUpload = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() => usePhotoUpload(onUpload))
    const file = makeFile('photo.heic', '')

    await act(async () => {
      await result.current.validateAndUpload(file)
    })

    expect(onUpload).toHaveBeenCalledWith(file)
    expect(toastError).not.toHaveBeenCalled()
  })

  it('принимает HEIC-фото, когда браузер всё же прислал корректный MIME', async () => {
    const onUpload = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() => usePhotoUpload(onUpload))
    const file = makeFile('photo.HEIC', 'image/heic')

    await act(async () => {
      await result.current.validateAndUpload(file)
    })

    expect(onUpload).toHaveBeenCalledWith(file)
  })

  it('принимает обычный JPEG с корректным MIME (регрессия базового случая)', async () => {
    const onUpload = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() => usePhotoUpload(onUpload))
    const file = makeFile('photo.jpg', 'image/jpeg')

    await act(async () => {
      await result.current.validateAndUpload(file)
    })

    expect(onUpload).toHaveBeenCalledWith(file)
  })

  it('отклоняет файл, который не похож на изображение ни по MIME, ни по расширению', async () => {
    const onUpload = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() => usePhotoUpload(onUpload))
    const file = makeFile('document.pdf', 'application/pdf')

    await act(async () => {
      await result.current.validateAndUpload(file)
    })

    expect(onUpload).not.toHaveBeenCalled()
    expect(toastError).toHaveBeenCalledWith('Можно загружать только изображения')
  })

  it('отклоняет файл больше 20 МБ', async () => {
    const onUpload = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() => usePhotoUpload(onUpload))
    const file = makeFile('big.jpg', 'image/jpeg', 21 * 1024 * 1024)

    await act(async () => {
      await result.current.validateAndUpload(file)
    })

    expect(onUpload).not.toHaveBeenCalled()
    expect(toastError).toHaveBeenCalledWith(expect.stringContaining('20 МБ'))
  })
})
