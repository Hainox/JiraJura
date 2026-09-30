import type { HatchFixState, HatchState, InspectionHatchOut } from '@/types'

export const inspectionHatchesKey = (inspectionId: string) => ['inspection-hatches', inspectionId]

// Та же причина отказа, что вернёт сервер при завершении обхода
// (hatch_completion_error в backend/app/services/hatches.py), — чтобы
// инспектор видел её заранее, а не только после нажатия «Завершить».
export function hatchCompletionProblem(items: InspectionHatchOut[] | undefined): string | null {
  if (!items?.length) return null
  const missing = items.filter((i) => i.hatch.is_active && !i.check).map((i) => `№${i.hatch.number}`)
  if (missing.length) return missing.length === 1 ? `Отметьте люк ${missing[0]}` : `Отметьте люки: ${missing.join(', ')}`
  const noPhoto = items
    .filter((i) => i.check && i.check.state !== 'ok' && i.check.photos.length === 0)
    .map((i) => `№${i.hatch.number}`)
  if (noPhoto.length) return `${noPhoto.length === 1 ? 'Нужно фото для люка' : 'Нужно фото для люков'} ${noPhoto.join(', ')}`
  return null
}

// Подписи — как в утверждённом макете и в backend/app/services/hatches.py
// (HATCH_STATE_SHORT / HATCH_STATE_FULL): короткие — в плашках и таблице
// журнала, полные — на кнопках выбора состояния.
export const HATCH_STATES: HatchState[] = ['ok', 'shifted', 'damaged', 'missing', 'sink']

export const HATCH_STATE_SHORT: Record<HatchState, string> = {
  ok: 'Исправен',
  shifted: 'Крышка смещена',
  damaged: 'Крышка повреждена',
  missing: 'Крышка отсутствует',
  sink: 'Провал вокруг люка',
}

export const HATCH_STATE_FULL: Record<HatchState, string> = {
  ok: 'Исправен',
  shifted: 'Крышка смещена / неплотно закрыта',
  damaged: 'Крышка повреждена',
  missing: 'Крышка отсутствует',
  sink: 'Провал / просадка вокруг люка',
}

export const HATCH_STATE_PILL: Record<HatchState, string> = {
  ok: 'bg-green-100 text-green-800',
  shifted: 'bg-red-100 text-red-800',
  damaged: 'bg-red-100 text-red-800',
  missing: 'bg-red-100 text-red-800',
  sink: 'bg-red-100 text-red-800',
}

export const HATCH_FIX_LABELS: Record<HatchFixState, string> = {
  none: '—',
  in_work: 'В работе',
  overdue: 'Просрочено',
  on_check: 'На проверке',
  accepted: 'Принято',
}

export const HATCH_FIX_PILL: Record<HatchFixState, string> = {
  none: 'text-gray-400',
  in_work: 'bg-amber-100 text-amber-800',
  overdue: 'bg-red-200 text-red-900 font-semibold',
  on_check: 'bg-blue-100 text-blue-800',
  accepted: 'bg-green-100 text-green-800',
}

export function hatchTitle(h: { number: string; owner?: string | null }): string {
  return `Люк №${h.number}${h.owner ? ` · ${h.owner}` : ''}`
}

export function mskTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('ru-RU', { timeZone: 'Europe/Moscow', hour: '2-digit', minute: '2-digit' })
}

export function mskDateTime(iso: string): string {
  return new Date(iso).toLocaleString('ru-RU', {
    timeZone: 'Europe/Moscow', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export function ruDate(isoDate: string): string {
  const [y, m, d] = isoDate.slice(0, 10).split('-')
  return `${d}.${m}.${y}`
}
