import { create } from 'zustand'
import type { UserOut } from '@/types'

interface AuthState {
  token: string | null
  user: UserOut | null
  isAuthenticated: boolean
  login: (token: string, user: UserOut) => void
  logout: () => void
  setUser: (user: UserOut) => void
}

// Читаем сохранённую сессию синхронно при создании стора, а не в useEffect
// после первого рендера — иначе ProtectedRoute успевает отрендерить
// <Navigate to="/login"> на isAuthenticated=false ДО того как сессия
// восстановится, и обратно на защищённую страницу уже никто не вернёт
// (LoginPage не следит за isAuthenticated). Из-за этого любой hard refresh
// или открытие PWA по прямой ссылке выкидывало на экран логина навсегда,
// даже с валидным токеном.
function loadStoredSession(): { token: string | null; user: UserOut | null } {
  const token = localStorage.getItem('access_token')
  const raw = localStorage.getItem('user')
  if (token && raw) {
    try {
      return { token, user: JSON.parse(raw) as UserOut }
    } catch {
      localStorage.removeItem('user')
    }
  }
  return { token: null, user: null }
}

const stored = loadStoredSession()

export const useAuthStore = create<AuthState>((set) => ({
  token: stored.token,
  user: stored.user,
  isAuthenticated: !!(stored.token && stored.user),

  login: (token, user) => {
    localStorage.setItem('access_token', token)
    localStorage.setItem('user', JSON.stringify(user))
    set({ token, user, isAuthenticated: true })
  },

  logout: () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('user')
    // Иначе на общем устройстве (планшет в поле) флаг форс-смены пароля
    // от ПРЕДЫДУЩЕГО пользователя переживает logout и цепляется к
    // следующему, кто залогинится, — даже если его собственный пароль
    // менять не нужно.
    localStorage.removeItem('force_pw_change')
    set({ token: null, user: null, isAuthenticated: false })
  },

  setUser: (user) => {
    localStorage.setItem('user', JSON.stringify(user))
    set({ user })
  },
}))
