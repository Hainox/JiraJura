import { describe, expect, it } from 'vitest'
import { FAQ_TOPICS, filterFaq } from './faq'

describe('FAQ_TOPICS', () => {
  it('у тем уникальные id (на них ведут ссылки /help?topic=...)', () => {
    const ids = FAQ_TOPICS.map((t) => t.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('у каждого вопроса есть роль, текст ответа и уникальная формулировка', () => {
    const questions = new Set<string>()
    for (const topic of FAQ_TOPICS) {
      expect(topic.items.length).toBeGreaterThan(0)
      for (const item of topic.items) {
        expect(item.roles.length).toBeGreaterThan(0)
        expect(item.a.trim().length).toBeGreaterThan(20)
        expect(questions.has(item.q)).toBe(false)
        questions.add(item.q)
      }
    }
  })
})

describe('filterFaq', () => {
  it('без запроса и с «Всем» возвращает все темы', () => {
    expect(filterFaq(FAQ_TOPICS, 'all', '')).toHaveLength(FAQ_TOPICS.length)
  })

  it('по роли оставляет только вопросы этой роли и убирает пустые темы', () => {
    const inspectorTopics = filterFaq(FAQ_TOPICS, 'inspector', '')
    expect(inspectorTopics.map((t) => t.id)).not.toContain('stat')
    for (const topic of inspectorTopics) {
      for (const item of topic.items) expect(item.roles).toContain('inspector')
    }
    expect(filterFaq(FAQ_TOPICS, 'admin', '').map((t) => t.id)).toContain('stat')
  })

  it('ищет по вопросу и ответу без учёта регистра и ё/е', () => {
    const byAnswer = filterFaq(FAQ_TOPICS, 'all', 'CAPS LOCK')
    expect(byAnswer.flatMap((t) => t.items.map((i) => i.q))).toContain('Пишет «Неверный логин или пароль»')

    const withYo = filterFaq(FAQ_TOPICS, 'all', 'её')
    const withYe = filterFaq(FAQ_TOPICS, 'all', 'ее')
    expect(withYo).toEqual(withYe)
  })

  it('все слова запроса должны встретиться, но не обязательно подряд', () => {
    const found = filterFaq(FAQ_TOPICS, 'all', 'пароль администратор')
    const questions = found.flatMap((t) => t.items.map((i) => i.q))
    expect(questions).toContain('Забыл пароль')
    expect(filterFaq(FAQ_TOPICS, 'all', 'пароль несуществующееслово')).toEqual([])
  })
})
