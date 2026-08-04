import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import RegisterPage from './RegisterPage'

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
    useParams: () => ({ token: 'test-invite-token' }),
  }
})

vi.mock('@/lib/api', () => ({
  authApi: {
    previewInvite: vi.fn().mockResolvedValue({
      full_name: 'Тестовый Пользователь',
      role: 'inspector',
    }),
    completeInvite: vi.fn().mockResolvedValue({
      access_token: 'new-token',
      user: { id: '1', login: 'newuser', full_name: 'Тестовый Пользователь', role: 'inspector' },
    }),
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

vi.mock('@/lib/roles', () => ({
  ROLE_LABELS: { inspector: 'Инспектор', reviewer: 'Проверяющий', admin: 'Администратор' },
}))

function renderRegister() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('RegisterPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('рендерит заголовок регистрации', () => {
    renderRegister()
    expect(screen.getByText('Регистрация')).toBeInTheDocument()
  })

  it('показывает приглашение после загрузки', async () => {
    renderRegister()
    // Ждём появления данных приглашения
    const nameEl = await screen.findByText(/Тестовый Пользователь/)
    expect(nameEl).toBeInTheDocument()
  })

  it('отображает поля пароля', async () => {
    renderRegister()
    const passwordInput = await screen.findByLabelText('Пароль')
    const confirmInput = screen.getByLabelText('Повторите пароль')
    expect(passwordInput).toBeInTheDocument()
    expect(confirmInput).toBeInTheDocument()
  })

  it('показывает ошибку при коротком пароле', async () => {
    renderRegister()
    const user = userEvent.setup()
    await screen.findByLabelText('Пароль')

    await user.type(screen.getByLabelText('Пароль'), '123')
    await user.type(screen.getByLabelText('Повторите пароль'), '123')
    await user.click(screen.getByRole('button', { name: /Зарегистрироваться/ }))

    const { notify } = await import('@/lib/toast')
    expect(notify.error).toHaveBeenCalledWith('Пароль должен быть не короче 8 символов')
  })

  it('показывает ошибку при несовпадении паролей', async () => {
    renderRegister()
    const user = userEvent.setup()
    await screen.findByLabelText('Пароль')

    await user.type(screen.getByLabelText('Пароль'), '12345678')
    await user.type(screen.getByLabelText('Повторите пароль'), 'different')
    await user.click(screen.getByRole('button', { name: /Зарегистрироваться/ }))

    const { notify } = await import('@/lib/toast')
    expect(notify.error).toHaveBeenCalledWith('Пароли не совпадают')
  })
})


