import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { authApi, describePasswordError } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { ArrowLeft, Save, Lock, User, Phone, Shield, MessageSquareWarning } from 'lucide-react'
import { notify as toast } from '@/lib/toast'

const ROLE_LABELS: Record<string, string> = {
  inspector: 'Инспектор',
  reviewer: 'Проверяющий',
  admin: 'Администратор',
}

export default function ProfilePage() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const setUser = useAuthStore((s) => s.setUser)

  const [fullName, setFullName] = useState(user?.full_name ?? '')
  const [phone, setPhone] = useState(user?.phone ?? '')

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPasswordForm, setShowPasswordForm] = useState(false)

  const updateMutation = useMutation({
    mutationFn: () => authApi.updateMe({ full_name: fullName, phone }),
    onSuccess: (data) => {
      setUser({ ...user!, full_name: data.full_name, phone: data.phone })
      toast.success('Профиль обновлён')
    },
    onError: () => toast.error('Ошибка обновления'),
  })

  const passwordMutation = useMutation({
    mutationFn: () => authApi.changePassword(newPassword, currentPassword),
    onSuccess: () => {
      toast.success('Пароль изменён')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setShowPasswordForm(false)
    },
    onError: (err: unknown) => toast.error(describePasswordError(err)),
  })

  const handlePasswordChange = () => {
    if (newPassword.length < 8) {
      toast.error('Пароль должен быть не короче 8 символов')
      return
    }
    if (newPassword !== confirmPassword) {
      toast.error('Пароли не совпадают')
      return
    }
    passwordMutation.mutate()
  }

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* Header */}
      <div className="bg-primary-800 text-white px-4 py-3 flex items-center gap-3 shrink-0">
        <button onClick={() => navigate('/')} className="p-1.5 rounded-lg hover:bg-primary-700 transition-colors">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <h1 className="text-lg font-bold">Мой профиль</h1>
          <p className="text-blue-200 text-xs">{user?.login}</p>
        </div>
      </div>

      <div className="overflow-y-auto flex-1 p-4 space-y-4">
        {/* Role badge */}
        <div className="card">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-primary-100 flex items-center justify-center">
              <Shield className="w-6 h-6 text-primary-600" />
            </div>
            <div>
              <div className="text-sm text-gray-500">Роль</div>
              <div className="font-semibold text-gray-800">
                {ROLE_LABELS[user?.role ?? ''] ?? user?.role}
              </div>
            </div>
          </div>
        </div>

        {/* Name & Phone */}
        <div className="card space-y-4">
          <h3 className="font-semibold text-sm text-gray-800">Личные данные</h3>

          <div>
            <label className="label">
              <User className="w-3.5 h-3.5 inline mr-1" /> ФИО
            </label>
            <input
              className="input-field"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
          </div>

          <div>
            <label className="label">
              <Phone className="w-3.5 h-3.5 inline mr-1" /> Телефон
            </label>
            <input
              className="input-field"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+7..."
            />
          </div>

          <button
            onClick={() => updateMutation.mutate()}
            disabled={updateMutation.isPending}
            className="btn-primary w-full flex items-center justify-center gap-2"
          >
            <Save className="w-4 h-4" />
            Сохранить изменения
          </button>
        </div>

        {/* Password change */}
        <div className="card space-y-4">
          <button
            onClick={() => setShowPasswordForm((v) => !v)}
            className="w-full flex items-center justify-between text-sm"
          >
            <span className="font-semibold text-gray-800 flex items-center gap-2">
              <Lock className="w-4 h-4" /> Сменить пароль
            </span>
            <span className="text-gray-400">{showPasswordForm ? '▲' : '▼'}</span>
          </button>

          {showPasswordForm && (
            <div className="space-y-3 pt-2 border-t">
              <input
                type="password"
                className="input-field"
                placeholder="Текущий пароль"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
              />
              <input
                type="password"
                className="input-field"
                placeholder="Новый пароль (мин. 8 символов)"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
              <p className="text-xs text-gray-500 -mt-2">
                Если короче 12 символов — нужны и буквы, и цифры. Простые пароли
                («12345678», «qwerty» и т.&nbsp;п.) не подойдут.
              </p>
              <input
                type="password"
                className="input-field"
                placeholder="Подтвердите новый пароль"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
              <button
                onClick={handlePasswordChange}
                disabled={passwordMutation.isPending || !currentPassword || !newPassword}
                className="btn-primary w-full disabled:opacity-50"
              >
                <Lock className="w-4 h-4 inline mr-1" />
                Установить новый пароль
              </button>
            </div>
          )}
        </div>

        {/* Обращения/жалобы — та же публичная форма /feedback, чтобы не
            искать ссылку отдельно: любой залогиненный сотрудник, а не
            только внешние пользователи, может пожаловаться на площадку
            или сообщить о технической проблеме в приложении. */}
        <button
          onClick={() => navigate('/feedback')}
          className="card w-full flex items-center gap-3 text-left hover:border-primary-300 transition-colors"
        >
          <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center shrink-0">
            <MessageSquareWarning className="w-5 h-5 text-red-600" />
          </div>
          <div>
            <div className="font-semibold text-sm text-gray-800">Сообщить о проблеме</div>
            <div className="text-xs text-gray-500">Жалоба на площадку или техническая проблема в приложении</div>
          </div>
        </button>
      </div>
    </div>
  )
}
