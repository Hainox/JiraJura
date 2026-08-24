import { useState, useCallback } from 'react'
import { notify as toast } from '@/lib/toast'
import { describeUploadError } from '@/lib/api'

// Синхронно с backend MAX_PHOTO_SIZE_MB (app/config.py) — раньше здесь
// стояло 10, а сервер реально принимал до 20: пользователей просили сжать
// фото, которое бэкенд и так бы принял без вопросов.
const MAX_SIZE_MB = 20
const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024

// Синхронно с backend _ALLOWED_PHOTO_EXTENSIONS (app/routers/issues.py) —
// расширения, а не file.type, потому что file.type для HEIC/HEIF ненадёжен
// именно там, где эти форматы чаще всего и приходят: с камеры iPhone в
// мобильном Safari/PWA браузер нередко отдаёт пустую строку вместо
// "image/heic". Раньше проверка была только по file.type.startsWith('image/')
// и реальному пользователю с iPhone блокировала загрузку валидного фото
// исправления с сообщением "можно загружать только изображения" — при
// том, что то же самое фото прошло бы без вопросов в любой другой форме
// загрузки в приложении (там такой проверки на клиенте нет вообще).
const ALLOWED_EXTENSIONS = ['jpg', 'jpeg', 'png', 'heic', 'heif', 'webp', 'gif']

function looksLikeImage(file: File): boolean {
  if (file.type.startsWith('image/')) return true
  const ext = file.name.split('.').pop()?.toLowerCase()
  return !!ext && ALLOWED_EXTENSIONS.includes(ext)
}

export function usePhotoUpload(onUpload: (file: File) => Promise<unknown>) {
  const [isUploading, setIsUploading] = useState(false)

  const validateAndUpload = useCallback(
    async (file: File | null | undefined) => {
      if (!file) return

      // Проверка типа
      if (!looksLikeImage(file)) {
        toast.error('Можно загружать только изображения')
        return
      }

      // Проверка размера
      if (file.size > MAX_SIZE_BYTES) {
        toast.error(`Файл больше ${MAX_SIZE_MB} МБ. Пожалуйста, сожмите изображение.`)
        return
      }

      // Проверка на пустой файл
      if (file.size === 0) {
        toast.error('Файл пустой')
        return
      }

      setIsUploading(true)
      try {
        await onUpload(file)
      } catch (err) {
        toast.error(describeUploadError(err))
      } finally {
        setIsUploading(false)
      }
    },
    [onUpload],
  )

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      validateAndUpload(file)
      // Сброс input для повторной загрузки того же файла
      e.target.value = ''
    },
    [validateAndUpload],
  )

  return { isUploading, handleFileInput, validateAndUpload }
}
