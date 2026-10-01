import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import HelpPage from './HelpPage'

const auth = vi.hoisted(() => ({ user: null as null | { role: string } }))

vi.mock('@/stores/auth', () => ({
  useAuthStore: (selector: (state: { user: typeof auth.user }) => unknown) => selector({ user: auth.user }),
}))

function renderHelp(url = '/help') {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/help" element={<HelpPage />} />
        <Route path="/login" element={<div>Экран входа</div>} />
        <Route path="/feedback" element={<div>Форма обращения</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

const topicButton = (title: string) => screen.getByRole('button', { name: new RegExp(`^${title}`) })

describe('HelpPage', () => {
  const scrollIntoView = vi.fn()

  beforeEach(() => {
    auth.user = null
    scrollIntoView.mockClear()
    Element.prototype.scrollIntoView = scrollIntoView
  })

  afterEach(() => {
    delete (Element.prototype as Partial<Element>).scrollIntoView
  })

  it('без входа показывает все темы свёрнутыми и выбирает «Всем»', () => {
    renderHelp()
    expect(screen.getByRole('heading', { name: 'Помощь' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Всем' })).toHaveAttribute('aria-pressed', 'true')
    expect(topicButton('Вход и установка')).toHaveAttribute('aria-expanded', 'false')
    expect(topicButton('Статистика и отчёты')).toBeInTheDocument()
    expect(topicButton('Люки САО')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Забыл пароль' })).not.toBeInTheDocument()
  })

  it('раскрывает тему и вопрос по нажатию', async () => {
    const user = userEvent.setup()
    renderHelp()
    await user.click(topicButton('Вход и установка'))
    expect(topicButton('Вход и установка')).toHaveAttribute('aria-expanded', 'true')

    const question = screen.getByRole('button', { name: 'Забыл пароль' })
    expect(question).toHaveAttribute('aria-expanded', 'false')
    await user.click(question)
    expect(question).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(/Сбросить пароль может только администратор округа/)).toBeInTheDocument()
  })

  it('поиск фильтрует вопросы и раскрывает найденные темы', async () => {
    const user = userEvent.setup()
    renderHelp()
    await user.type(screen.getByRole('searchbox', { name: 'Поиск по вопросам' }), 'caps lock')

    expect(screen.getByRole('button', { name: 'Пишет «Неверный логин или пароль»' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Статистика и отчёты/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Забыл пароль' })).not.toBeInTheDocument()
  })

  it('при пустом результате предлагает написать в поддержку', async () => {
    const user = userEvent.setup()
    renderHelp()
    await user.type(screen.getByRole('searchbox', { name: 'Поиск по вопросам' }), 'абракадабра')

    const empty = screen.getByRole('status')
    expect(within(empty).getByText(/Ничего не нашлось/)).toBeInTheDocument()
    await user.click(within(empty).getByRole('button', { name: 'Написать в поддержку' }))
    expect(screen.getByText('Форма обращения')).toBeInTheDocument()
  })

  it('выбирает роль вошедшего пользователя и переключается чипами', async () => {
    auth.user = { role: 'inspector' }
    const user = userEvent.setup()
    renderHelp()

    expect(screen.getByRole('button', { name: 'Инспектор' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByRole('button', { name: /^Статистика и отчёты/ })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Округ' }))
    expect(screen.getByRole('button', { name: 'Округ' })).toHaveAttribute('aria-pressed', 'true')
    expect(topicButton('Статистика и отчёты')).toBeInTheDocument()
  })

  it('«Район» — это роль reviewer', () => {
    auth.user = { role: 'reviewer' }
    renderHelp()
    expect(screen.getByRole('button', { name: 'Район' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('?topic= открывает тему и прокручивает к ней, даже если роль её скрыла бы', () => {
    auth.user = { role: 'inspector' }
    renderHelp('/help?topic=stat')

    expect(screen.getByRole('button', { name: 'Всем' })).toHaveAttribute('aria-pressed', 'true')
    expect(topicButton('Статистика и отчёты')).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('button', { name: 'Что такое «Охват»?' })).toBeInTheDocument()
    expect(scrollIntoView).toHaveBeenCalled()
    expect(scrollIntoView.mock.contexts[0]).toBe(document.getElementById('faq-topic-stat'))
  })

  it('кнопка «Назад» без истории ведёт на вход, если не вошли', async () => {
    const user = userEvent.setup()
    renderHelp()
    await user.click(screen.getByRole('button', { name: 'Назад' }))
    expect(screen.getByText('Экран входа')).toBeInTheDocument()
  })

  it('внизу есть карточка «Не нашли ответ?» со ссылкой на поддержку', async () => {
    const user = userEvent.setup()
    renderHelp()
    expect(screen.getByText('Не нашли ответ?')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Написать в поддержку' }))
    expect(screen.getByText('Форма обращения')).toBeInTheDocument()
  })
})
