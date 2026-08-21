import { describe, expect, it } from 'vitest'
import { currentMskWeek, mskDateString, percentageColor, previousMskWeek } from './statistics'

describe('statistics calendar helpers', () => {
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
})
