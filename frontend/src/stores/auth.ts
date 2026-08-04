import { create } from 'zustand'
import type { UserOut } from '@/types'

interface AuthState {
  token: string | null
  user: UserOut | null
  isAuthenticated: boolean
  login: (token: string, user: UserOut) => void
  logout: () => void
  hydrate: () => void
  setUser: (user: UserOut) => void
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,
  isAuthenticated: false,

  login: (token, user) => {
    localStorage.setItem('access_token', token)
    localStorage.setItem('user', JSON.stringify(user))
    set({ token, user, isAuthenticated: true })
  },

  logout: () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('user')
    set({ token: null, user: null, isAuthenticated: false })
  },

  hydrate: () => {
    const token = localStorage.getItem('access_token')
    const raw = localStorage.getItem('user')
    if (token && raw) {
      try {
        const user = JSON.parse(raw) as UserOut
        set({ token, user, isAuthenticated: true })
      } catch {
        localStorage.removeItem('user')
      }
    }
  },

  setUser: (user) => {
    localStorage.setItem('user', JSON.stringify(user))
    set({ user })
  },
}))
