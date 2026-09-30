export const CHILD_TYPE = 'Детская площадка'
export const SPORT_TYPE = 'Спортивная площадка'

// Статусы обхода, при которых площадка считается обойдённой сегодня
// (счётчик «Сегодня обойдено» и фильтр «Только необойдённые»).
export const VISITED_STATUSES = new Set(['completed', 'issues_found', 'critical'])

export type CoverageState = 'not_inspected' | 'in_progress' | 'completed' | 'violations'

// Один источник цветов и для меток, и для легенды: раньше легенда рисовалась
// tailwind-классами отдельно от hex-цветов меток, и необойдённая
// спортивная площадка была зелёной — тем же цветом, что «Завершена».
export const COVERAGE_LEGEND: { state: CoverageState; label: string; color: string }[] = [
  { state: 'not_inspected', label: 'Не обойдена', color: '#2563eb' },
  { state: 'in_progress', label: 'В процессе', color: '#ca8a04' },
  { state: 'completed', label: 'Завершена', color: '#16a34a' },
  { state: 'violations', label: 'С нарушениями', color: '#dc2626' },
]

const COLOR_BY_STATE = Object.fromEntries(
  COVERAGE_LEGEND.map(({ state, color }) => [state, color]),
) as Record<CoverageState, string>

/** Состояние площадки на карте по статусу её сегодняшнего обхода
 * (undefined — сегодня обхода нет). */
export function coverageState(status?: string | null): CoverageState {
  if (status === 'completed') return 'completed'
  if (status === 'in_progress') return 'in_progress'
  if (status === 'issues_found' || status === 'critical') return 'violations'
  return 'not_inspected'
}

export function markerColor(status?: string | null): string {
  return COLOR_BY_STATE[coverageState(status)]
}

/** Тип площадки различается буквой, а не цветом — цвет занят статусом. */
export function markerLabel(siteType: string | undefined, status?: string | null): string {
  if (coverageState(status) === 'completed') return '✓'
  return siteType === CHILD_TYPE ? 'Д' : 'С'
}

export function countVisitedToday(
  siteIds: string[],
  statusBySite: Record<string, { status: string } | undefined>,
): number {
  return siteIds.filter((id) => {
    const status = statusBySite[id]?.status
    return !!status && VISITED_STATUSES.has(status)
  }).length
}
