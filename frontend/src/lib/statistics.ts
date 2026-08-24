const MSK_TIMEZONE = 'Europe/Moscow'
export type StatisticsPreset = 'day' | 'week' | 'month'

export function mskDateString(now = new Date()): string {
  const parts = new Intl.DateTimeFormat('en', {
    timeZone: MSK_TIMEZONE,
    year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(now)
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]))
  return `${values.year}-${values.month}-${values.day}`
}

function shiftCalendarDate(value: string, days: number): string {
  const date = new Date(`${value}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

export function currentMskWeek(now = new Date()): readonly [string, string] {
  const today = mskDateString(now)
  const weekday = new Date(`${today}T00:00:00Z`).getUTCDay()
  const daysSinceMonday = (weekday + 6) % 7
  return [shiftCalendarDate(today, -daysSinceMonday), today] as const
}

export function previousMskWeek(now = new Date()): readonly [string, string] {
  const [thisMonday] = currentMskWeek(now)
  return [shiftCalendarDate(thisMonday, -7), shiftCalendarDate(thisMonday, -1)] as const
}

export function periodRange(preset: StatisticsPreset, now = new Date()): readonly [string, string] {
  const today = mskDateString(now)
  if (preset === 'day') return [today, today] as const
  if (preset === 'week') return currentMskWeek(now)
  return [`${today.slice(0, 7)}-01`, today] as const
}

export function percentageColor(value: number): string {
  if (value >= 100) return '#63BE7B'
  if (value >= 70) return '#FFD966'
  if (value >= 50) return '#F4B183'
  return '#E06666'
}

/** Soft six-step coverage scale. Zero is data, not an automatic failure. */
export function coverageColor(value: number): string {
  if (value >= 90) return '#63BE7B'
  if (value >= 75) return '#A9D18E'
  if (value >= 60) return '#DDEB9A'
  if (value >= 40) return '#FFD966'
  if (value >= 20) return '#F4B183'
  return '#E06666'
}

export function withTotalsRow<T>(rows: readonly T[], totals: T): T[] {
  return [...rows, totals]
}
