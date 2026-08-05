import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/lib/api'
import { notify as toast } from '@/lib/toast'
import { Lock } from 'lucide-react'

export default function ChangePasswordPage() {
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)
  const loginStore = useAuthStore((s) => s.login)
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (password.length < 8) {
      toast.error('Пароль должен быть не короче 8 символов')
      return
    }
    if (password !== confirm) {
      toast.error('Пароли не совпадают')
      return
    }
    setLoading(true)
    try {
      const res = await authApi.changePassword(password)
      loginStore(res.access_token, res.user)
      localStorage.removeItem('force_pw_change')
      toast.success(`Добро пожаловать, ${res.user.full_name}!`)
      navigate('/')
    } catch {
      toast.error('Не удалось сменить пароль')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="h-full flex items-center justify-center bg-gradient-to-b from-amber-800 to-amber-600 px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-white/20 rounded-2xl mb-4">
            <Lock className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-xl font-bold text-white">Смените пароль</h1>
          <p className="text-amber-200 mt-1 text-sm">
            Администратор сбросил ваш пароль. Придумайте новый для продолжения работы.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="card backdrop-blur-sm bg-white/95">
          <div className="mb-4">
            <label className="label" htmlFor="new-password">
              Новый пароль
            </label>
            <input
              id="new-password"
              type="password"
              className="input-field"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Минимум 8 символов"
              autoComplete="new-password"
              required
              autoFocus
            />
          </div>
          <div className="mb-6">
            <label className="label" htmlFor="confirm-password">
              Подтвердите пароль
            </label>
            <input
              id="confirm-password"
              type="password"
              className="input-field"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="Повторите пароль"
              autoComplete="new-password"
              required
            />
          </div>
          <button type="submit" disabled={loading} className="btn-primary w-full">
            {loading ? 'Сохранение...' : 'Сохранить и продолжить'}
          </button>
        </form>
      </div>
    </div>
  )
}
