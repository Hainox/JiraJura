import { describe, expect, it } from 'vitest'
import {
  CHILD_TYPE, COVERAGE_LEGEND, SPORT_TYPE,
  countVisitedToday, coverageState, markerColor, markerLabel,
} from './mapMarkers'

const legendColor = (label: string) => COVERAGE_LEGEND.find((l) => l.label === label)!.color

describe('цвета меток на карте', () => {
  it('необойдённая площадка одного цвета независимо от типа — как «Не обойдена» в легенде', () => {
    expect(markerColor(undefined)).toBe(legendColor('Не обойдена'))
    expect(markerLabel(CHILD_TYPE, undefined)).toBe('Д')
    expect(markerLabel(SPORT_TYPE, undefined)).toBe('С')
    expect(markerColor(undefined)).not.toBe(legendColor('Завершена'))
  })

  it('каждый статус обхода совпадает с цветом своей строки легенды', () => {
    expect(markerColor('in_progress')).toBe(legendColor('В процессе'))
    expect(markerColor('completed')).toBe(legendColor('Завершена'))
    expect(markerColor('issues_found')).toBe(legendColor('С нарушениями'))
    expect(markerColor('critical')).toBe(legendColor('С нарушениями'))
    expect(markerColor('planned')).toBe(legendColor('Не обойдена'))
  })

  it('у легенды четыре разных цвета', () => {
    const colors = COVERAGE_LEGEND.map((l) => l.color)
    expect(new Set(colors).size).toBe(4)
  })

  it('завершённая площадка отмечается галочкой, остальные — буквой типа', () => {
    expect(markerLabel(SPORT_TYPE, 'completed')).toBe('✓')
    expect(markerLabel(CHILD_TYPE, 'completed')).toBe('✓')
    expect(markerLabel(SPORT_TYPE, 'issues_found')).toBe('С')
    expect(coverageState('in_progress')).toBe('in_progress')
  })
})

describe('countVisitedToday', () => {
  it('считает только показанные площадки с завершённым сегодня обходом', () => {
    const statuses = {
      a: { status: 'completed' },
      b: { status: 'in_progress' },
      c: { status: 'critical' },
      hidden: { status: 'completed' },
    }
    expect(countVisitedToday(['a', 'b', 'c', 'd'], statuses)).toBe(2)
  })
})
