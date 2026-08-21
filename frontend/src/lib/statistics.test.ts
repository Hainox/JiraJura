import { describe, expect, it } from 'vitest'
import { currentMskWeek, mskDateString, percentageColor, periodRange, previousMskWeek, withTotalsRow } from './statistics'
import type { StatsDistrictRow } from '@/types'

describe('statistics calendar helpers', () => {
  it('appends the server-calculated weighted total row without modifying districts', () => {
    const district = { district_id: 'district', district_name: 'Аэропорт' } as StatsDistrictRow
    const total = { district_id: 'total', district_name: 'ВСЕГО', coverage_pct: 75, issues_closed_pct: 67 } as StatsDistrictRow

    expect(withTotalsRow([district], total)).toEqual([district, total])
    expect(withTotalsRow([], total)).toEqual([total])
  })

  it('uses the Moscow date across the UTC midnight boundary', () => {
    const instant = new Date('2026-08-16T21:30:00Z') // 00:30 Monday MSK
    expect(mskDateString(instant)).toBe('2026-08-17')
    expect(currentMskWeek(instant)).toEqual(['2026-08-17', '2026-08-17'])
    expect(previousMskWeek(instant)).toEqual(['2026-08-10', '2026-08-16'])
  })

  it.each([[49, '#E06666'], [50, '#F4B183'], [69, '#F4B183'],
    [70, '#FFD966'], [99, '#FFD966'], [100, '#63BE7B']] as const)(
    'maps %s to the shared report color', (value, color) => {
      expect(percentageColor(value)).toBe(color)
    },
  )

  it.each([
    ['day', ['2026-08-17', '2026-08-17']],
    ['week', ['2026-08-17', '2026-08-17']],
    ['month', ['2026-08-01', '2026-08-17']],
  ] as const)('builds the %s preset in Moscow time', (preset, expected) => {
    expect(periodRange(preset, new Date('2026-08-16T21:30:00Z'))).toEqual(expected)
  })
})
