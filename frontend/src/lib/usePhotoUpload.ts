import { useState, useCallback } from 'react'
import { notify as toast } from '@/lib/toast'
import { describeUploadError } from '@/lib/api'

// Синхронно с backend MAX_PHOTO_SIZE_MB (app/config.py) — раньше здесь
// стояло 10, а сервер реально принимал до 20: пользователей просили сжать
// фото, которое бэкенд и так бы принял без вопросов.
const MAX_SIZE_MB = 20
const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024

export function usePhotoUpload(onUpload: (file: File) => Promise<unknown>) {
  const [isUploading, setIsUploading] = useState(false)

  const validateAndUpload = useCallback(
    async (file: File | null | undefined) => {
      if (!file) return

      // Проверка типа
      if (!file.type.startsWith('image/')) {
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
