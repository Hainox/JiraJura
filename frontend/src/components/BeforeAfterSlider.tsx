import { useState, useRef, useCallback, useEffect } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

interface Props {
  /** URL фото ДО (из обхода) */
  beforeUrl?: string
  /** URL фото ПОСЛЕ (исправления) */
  afterUrl?: string
  /** Метка левой стороны */
  beforeLabel?: string
  /** Метка правой стороны */
  afterLabel?: string
}

export default function BeforeAfterSlider({
  beforeUrl,
  afterUrl,
  beforeLabel = 'ДО',
  afterLabel = 'ПОСЛЕ',
}: Props) {
  const [position, setPosition] = useState(50) // % от левого края
  const [dragging, setDragging] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const handleMove = useCallback(
    (clientX: number) => {
      if (!containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      const x = clientX - rect.left
      const pct = Math.max(5, Math.min(95, (x / rect.width) * 100))
      setPosition(pct)
    },
    []
  )

  const onMouseDown = useCallback(() => setDragging(true), [])
  const onTouchStart = useCallback(() => setDragging(true), [])

  useEffect(() => {
    if (!dragging) return
    const onMouseMove = (e: MouseEvent) => {
      e.preventDefault()
      handleMove(e.clientX)
    }
    const onTouchMove = (e: TouchEvent) => {
      handleMove(e.touches[0].clientX)
    }
    const onEnd = () => setDragging(false)

    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onEnd)
    window.addEventListener('touchmove', onTouchMove, { passive: true })
    window.addEventListener('touchend', onEnd)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onEnd)
      window.removeEventListener('touchmove', onTouchMove)
      window.removeEventListener('touchend', onEnd)
    }
  }, [dragging, handleMove])

  // Если нет обеих картинок
  if (!beforeUrl && !afterUrl) {
    return (
      <div className="bg-gray-100 rounded-xl flex items-center justify-center h-48 text-gray-400 text-sm">
        Нет фото для сравнения
      </div>
    )
  }

  // Если только одна сторона — показываем одно фото с меткой
  if (!beforeUrl || !afterUrl) {
    const url = beforeUrl || afterUrl!
    const label = beforeUrl ? beforeLabel : afterLabel
    const borderColor = beforeUrl ? 'border-blue-200' : 'border-green-200'
    return (
      <div className="space-y-2">
        <span className={`inline-block text-xs font-medium px-2 py-0.5 rounded-full ${beforeUrl ? 'bg-blue-100 text-blue-700' : 'bg-green-100 text-green-700'}`}>
          {label}
        </span>
        <a href={url} target="_blank" rel="noreferrer" className={`block w-full h-72 bg-gray-900 rounded-xl border-2 ${borderColor} overflow-hidden hover:opacity-90 transition-opacity`}>
          <img
            src={url}
            alt={label}
            className="w-full h-full object-contain"
          />
        </a>
        {!beforeUrl && (
          <p className="text-xs text-gray-400 italic">Фото ДО отсутствует</p>
        )}
        {!afterUrl && (
          <p className="text-xs text-gray-400 italic">Фото ПОСЛЕ ещё не загружено</p>
        )}
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      className="relative w-full h-72 bg-gray-900 select-none rounded-xl overflow-hidden cursor-col-resize"
      onMouseDown={onMouseDown}
      onTouchStart={onTouchStart}
    >
      {/* Левая сторона — ДО. object-contain (не cover) — иначе телефонные
          фото произвольных пропорций обрезаются в фиксированную коробку,
          и на сравнении ДО/ПОСЛЕ часто пропадает как раз то место, где
          видно нарушение/исправление. */}
      <div className="absolute inset-0 overflow-hidden" style={{ clipPath: `inset(0 ${100 - position}% 0 0)` }}>
        <img src={beforeUrl} alt="ДО" className="w-full h-full object-contain" />
        <span className="absolute top-2 left-2 bg-blue-600 text-white text-xs font-bold px-2 py-0.5 rounded-full shadow">
          {beforeLabel}
        </span>
      </div>

      {/* Правая сторона — ПОСЛЕ */}
      <div className="absolute inset-0 overflow-hidden" style={{ clipPath: `inset(0 0 0 ${position}%)` }}>
        <img src={afterUrl} alt="ПОСЛЕ" className="w-full h-full object-contain" />
        <span className="absolute top-2 right-2 bg-green-600 text-white text-xs font-bold px-2 py-0.5 rounded-full shadow">
          {afterLabel}
        </span>
      </div>

      {/* Линия-разделитель */}
      <div
        className="absolute top-0 bottom-0 w-1 bg-white shadow-lg pointer-events-none"
        style={{ left: `${position}%` }}
      >
        {/* Ручка */}
        <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-8 h-8 bg-white rounded-full shadow-lg border-2 border-gray-300 flex items-center justify-center pointer-events-auto">
          <ChevronLeft className="w-3 h-3 text-gray-400 -mr-0.5" />
          <ChevronRight className="w-3 h-3 text-gray-400 -ml-0.5" />
        </div>
      </div>

      {/* Затемнение для курсора */}
      {dragging && (
        <div className="absolute inset-0 bg-black/10 pointer-events-none" />
      )}
    </div>
  )
}
