import { describe, expect, it } from 'vitest'
import {
  coverageColor, currentMskWeek, mskDateString, percentageColor, periodRange,
  previousMskWeek, qualityColor, remediationMetricLabel, withTotalsRow,
} from './statistics'
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

  it.each([[0, '#E06666'], [20, '#F4B183'], [40, '#FFD966'], [60, '#DDEB9A'], [75, '#A9D18E'], [90, '#63BE7B']] as const)(
    'uses a softer six-step traffic light for coverage: %s', (value, color) => {
      expect(coverageColor(value)).toBe(color)
    },
  )

  it.each([
    [0, 'direct', '#E06666'], [19, 'direct', '#E06666'], [20, 'direct', '#F4B183'],
    [39, 'direct', '#F4B183'], [40, 'direct', '#F9CB9C'], [59, 'direct', '#F9CB9C'],
    [60, 'direct', '#FFD966'], [74, 'direct', '#FFD966'], [75, 'direct', '#A9D18E'],
    [89, 'direct', '#A9D18E'], [90, 'direct', '#63BE7B'], [100, 'direct', '#63BE7B'],
    [0, 'inverse', '#63BE7B'], [10, 'inverse', '#63BE7B'], [11, 'inverse', '#A9D18E'],
    [26, 'inverse', '#FFD966'], [41, 'inverse', '#F9CB9C'], [61, 'inverse', '#F4B183'],
    [81, 'inverse', '#E06666'], [100, 'inverse', '#E06666'],
  ] as const)('maps %s%% quality in %s direction to %s', (value, direction, color) => {
    expect(qualityColor(value, direction)).toBe(color)
  })

  it('does not colour an absent quality denominator as a failure', () => {
    expect(qualityColor(null, 'direct')).toBeUndefined()
    expect(qualityColor(null, 'inverse')).toBeUndefined()
  })

  it('formats remediation percentages as X из Y · N%', () => {
    expect(remediationMetricLabel(5, 10, 50)).toBe('5 из 10 · 50%')
  })

  it('renders a missing remediation denominator as a neutral dash', () => {
    expect(remediationMetricLabel(0, 0, null)).toBe('—')
  })

  it.each([
    ['day', ['2026-08-17', '2026-08-17']],
    ['week', ['2026-08-17', '2026-08-17']],
    ['month', ['2026-08-01', '2026-08-17']],
  ] as const)('builds the %s preset in Moscow time', (preset, expected) => {
    expect(periodRange(preset, new Date('2026-08-16T21:30:00Z'))).toEqual(expected)
  })
})
