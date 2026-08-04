import { describe, it, expect, beforeEach } from 'vitest'
import { useAuthStore } from './auth'
import type { UserOut } from '@/types'

const mockUser: UserOut = {
  id: 'test-user-id',
  login: 'inspector1',
  full_name: 'Тестовый Инспектор',
  role: 'inspector',
  district_id: 'district-1',
  phone: '+79991234567',
}

describe('useAuthStore', () => {
  beforeEach(() => {
    localStorage.clear()
    useAuthStore.setState({
      user: null,
      token: null,
      isAuthenticated: false,
    })
  })

  it('изначально не аутентифицирован', () => {
    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(false)
    expect(state.user).toBeNull()
    expect(state.token).toBeNull()
  })

  it('login сохраняет токен и пользователя', () => {
    act(() => {
      useAuthStore.getState().login('test-token-123', mockUser)
    })

    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(true)
    expect(state.token).toBe('test-token-123')
    expect(state.user).toEqual(mockUser)
    expect(localStorage.getItem('access_token')).toBe('test-token-123')
  })

  it('logout очищает состояние и localStorage', () => {
    act(() => {
      useAuthStore.getState().login('test-token-123', mockUser)
    })
    act(() => {
      useAuthStore.getState().logout()
    })

    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(false)
    expect(state.user).toBeNull()
    expect(state.token).toBeNull()
    expect(localStorage.getItem('access_token')).toBeNull()
  })

  it('setUser обновляет поля пользователя', () => {
    act(() => {
      useAuthStore.getState().login('token', mockUser)
    })
    act(() => {
      useAuthStore.getState().setUser({ ...mockUser, full_name: 'Новое Имя', phone: '+79990001122' })
    })

    const state = useAuthStore.getState()
    expect(state.user?.full_name).toBe('Новое Имя')
    expect(state.user?.phone).toBe('+79990001122')
    expect(state.user?.login).toBe('inspector1') // не изменился
  })
})

// Небольшой хелпер для act без импорта из React
function act(fn: () => void) {
  fn()
}
