import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import LoginPage from './LoginPage'

// Мокаем auth store
const mockLogin = vi.fn()
const mockNavigate = vi.fn()

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ login: mockLogin }),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

// Мокаем api
vi.mock('@/lib/api', () => ({
  authApi: {
    login: vi.fn(),
  },
}))

vi.mock('@/lib/toast', () => ({
  notify: {
    success: vi.fn(),
    error: vi.fn(),
    loading: vi.fn(),
    dismiss: vi.fn(),
    promise: vi.fn(),
  },
}))

function renderLogin() {
  const queryClient = new QueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('рендерит форму логина', () => {
    renderLogin()
    expect(screen.getByLabelText('Логин')).toBeInTheDocument()
    expect(screen.getByLabelText('Пароль')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Войти' })).toBeInTheDocument()
  })

  it('рендерит заголовок', () => {
    renderLogin()
    expect(screen.getByText('Журнал обхода площадок')).toBeInTheDocument()
    expect(screen.getByText('САО г. Москвы')).toBeInTheDocument()
  })

  it('кнопка "Войти" есть и не disabled изначально', () => {
    renderLogin()
    const btn = screen.getByRole('button', { name: 'Войти' })
    expect(btn).not.toBeDisabled()
  })

  it('поля принимают ввод', async () => {
    renderLogin()
    const user = userEvent.setup()
    const loginInput = screen.getByLabelText('Логин')
    const passwordInput = screen.getByLabelText('Пароль')

    await user.type(loginInput, 'testuser')
    await user.type(passwordInput, 'testpass')

    expect(loginInput).toHaveValue('testuser')
    expect(passwordInput).toHaveValue('testpass')
  })

  it('показывает ошибку при неверном логине', async () => {
    const { authApi } = await import('@/lib/api')
    vi.mocked(authApi.login).mockRejectedValueOnce(new Error('Unauthorized'))

    renderLogin()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Логин'), 'bad')
    await user.type(screen.getByLabelText('Пароль'), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Войти' }))

    const { notify } = await import('@/lib/toast')
    // Ждём асинхронного вызова
    await vi.waitFor(() => {
      expect(notify.error).toHaveBeenCalledWith('Неверный логин или пароль')
    })
  })
})
