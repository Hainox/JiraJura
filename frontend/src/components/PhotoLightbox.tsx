import { useEffect } from 'react'
import { X } from 'lucide-react'

// Раньше фото открывались через <a href=... target="_blank"> — в PWA,
// запущенном в standalone-режиме (иконка с домашнего экрана на iOS Safari),
// это уводит с единственной "вкладки" на голый URL картинки БЕЗ адресной
// строки и кнопки "назад": закрыть нечем, приходится перезагружать всё
// приложение. Полноэкранный оверлей внутри самого SPA не покидает
// приложение вообще — closable кнопкой, тапом по фону и Escape.
export default function PhotoLightbox({ url, onClose }: { url: string | null; onClose: () => void }) {
  useEffect(() => {
    if (!url) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [url, onClose])

  if (!url) return null

  return (
    <div
      className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <button
        onClick={onClose}
        className="absolute top-4 right-4 p-2.5 rounded-full bg-white/10 hover:bg-white/20 text-white z-10"
        aria-label="Закрыть"
      >
        <X className="w-6 h-6" />
      </button>
      <img
        src={url}
        alt=""
        className="max-w-full max-h-full object-contain"
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  )
}
