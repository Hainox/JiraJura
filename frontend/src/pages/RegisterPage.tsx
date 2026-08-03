import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { authApi } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { ROLE_LABELS } from '@/lib/roles'
import type { Role } from '@/types'
import toast from 'react-hot-toast'
import { Shield } from 'lucide-react'

export default function RegisterPage() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const loginStore = useAuthStore((s) => s.login)

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const { data: invite, isLoading, isError } = useQuery({
    queryKey: ['invite', token],
    queryFn: () => authApi.previewInvite(token!),
    enabled: !!token,
    retry: false,
  })

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
    setSubmitting(true)
    try {
      const res = await authApi.completeInvite(token!, password)
      loginStore(res.access_token, res.user)
      toast.success(`Добро пожаловать, ${res.user.full_name}!`)
      navigate('/')
    } catch {
      toast.error('Не удалось завершить регистрацию — ссылка могла устареть')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="h-full flex items-center justify-center bg-gradient-to-b from-blue-900 to-blue-700 px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-white/20 rounded-2xl mb-4">
            <Shield className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white">Регистрация</h1>
          <p className="text-blue-200 mt-1">Журнал обхода площадок САО</p>
        </div>

        <div className="card backdrop-blur-sm bg-white/95">
          {isLoading && <p className="text-center text-gray-500">Проверяем приглашение…</p>}

          {isError && (
            <p className="text-center text-red-600">
              Ссылка недействительна, устарела или уже использована. Обратитесь к администратору за новым приглашением.
            </p>
          )}

          {invite && (
            <form onSubmit={handleSubmit}>
              <p className="mb-4 text-gray-700">
                Регистрация для <b>{invite.full_name}</b>, роль «{ROLE_LABELS[invite.role as Role] ?? invite.role}»
              </p>
              <div className="mb-4">
                <label className="label" htmlFor="password">Пароль</label>
                <input
                  id="password"
                  type="password"
                  className="input-field"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="new-password"
                  minLength={8}
                  required
                />
              </div>
              <div className="mb-6">
                <label className="label" htmlFor="confirm">Повторите пароль</label>
                <input
                  id="confirm"
                  type="password"
                  className="input-field"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  autoComplete="new-password"
                  minLength={8}
                  required
                />
              </div>
              <button type="submit" disabled={submitting} className="btn-primary w-full">
                {submitting ? 'Регистрируем…' : 'Зарегистрироваться'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
