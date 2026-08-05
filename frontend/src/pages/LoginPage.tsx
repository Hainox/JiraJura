import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/lib/api'
import { notify as toast } from '@/lib/toast'
import { Shield } from 'lucide-react'

export default function LoginPage() {
  const [loginValue, setLoginValue] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const loginStore = useAuthStore((s) => s.login)
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      const res = await authApi.login({ login: loginValue, password })
      loginStore(res.access_token, res.user)
      if (res.must_change_password) {
        localStorage.setItem('force_pw_change', '1')
        navigate('/change-password')
      } else {
        toast.success(`Добро пожаловать, ${res.user.full_name}!`)
        navigate('/')
      }
    } catch {
      toast.error('Неверный логин или пароль')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="h-full flex items-center justify-center bg-gradient-to-b from-blue-900 to-blue-700 px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-white/20 rounded-2xl mb-4">
            <Shield className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white">Журнал обхода площадок</h1>
          <p className="text-blue-200 mt-1">САО г. Москвы</p>
        </div>

        <form onSubmit={handleSubmit} className="card backdrop-blur-sm bg-white/95">
          <div className="mb-4">
            <label className="label" htmlFor="username">Логин</label>
            <input
              id="username"
              type="text"
              className="input-field"
              value={loginValue}
              onChange={(e) => setLoginValue(e.target.value)}
              autoComplete="username"
              required
            />
          </div>
          <div className="mb-6">
            <label className="label" htmlFor="password">Пароль</label>
            <input
              id="password"
              type="password"
              className="input-field"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>
          <button type="submit" disabled={loading} className="btn-primary w-full">
            {loading ? 'Вход...' : 'Войти'}
          </button>
        </form>
      </div>
    </div>
  )
}
