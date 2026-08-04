import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { authApi, districtsApi } from '@/lib/api'
import { ROLES, ROLE_LABELS } from '@/lib/roles'
import type { Role, UserAdminOut, UserInviteCreated } from '@/types'
import { notify as toast } from '@/lib/toast'
import {
  ArrowLeft, UserPlus, Copy, Check, Trash2, Key, Edit3, X, Search
} from 'lucide-react'

export default function AdminUsersPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [showInviteForm, setShowInviteForm] = useState(false)
  const [login, setLogin] = useState('')
  const [fullName, setFullName] = useState('')
  const [role, setRole] = useState<Role>('inspector')
  const [districtId, setDistrictId] = useState('')
  const [lastInvite, setLastInvite] = useState<UserInviteCreated | null>(null)
  const [copied, setCopied] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  // Модалка редактирования
  const [editUser, setEditUser] = useState<UserAdminOut | null>(null)
  const [editFullName, setEditFullName] = useState('')
  const [editPhone, setEditPhone] = useState('')
  const [editRole, setEditRole] = useState<Role>('inspector')
  const [editDistrictId, setEditDistrictId] = useState('')

  // Подтверждение удаления
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)
  const [resetPasswordId, setResetPasswordId] = useState<string | null>(null)
  const [newPassword, setNewPassword] = useState<string | null>(null)

  const { data: users } = useQuery({ queryKey: ['admin-users'], queryFn: authApi.listUsers })
  const { data: districts } = useQuery({ queryKey: ['districts'], queryFn: districtsApi.list })

  const districtName = (id?: string) => districts?.find((d) => d.id === id)?.name ?? '—'

  const filteredUsers = users?.filter((u) => {
    if (!searchQuery) return true
    const q = searchQuery.toLowerCase()
    return (
      u.full_name.toLowerCase().includes(q) ||
      u.login.toLowerCase().includes(q) ||
      (u.phone && u.phone.includes(q)) ||
      districtName(u.district_id).toLowerCase().includes(q)
    )
  })

  const inviteMutation = useMutation({
    mutationFn: () =>
      authApi.createInvite({
        login,
        full_name: fullName,
        role,
        district_id: districtId || undefined,
      }),
    onSuccess: (invite) => {
      setLastInvite(invite)
      setLogin('')
      setFullName('')
      setRole('inspector')
      setDistrictId('')
      toast.success('Приглашение создано')
    },
    onError: () => toast.error('Не удалось создать приглашение — проверьте, не занят ли логин'),
  })

  const toggleActiveMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      authApi.updateUser(id, { is_active }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['admin-users'] }) },
    onError: () => toast.error('Не удалось изменить статус'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => authApi.deleteUser(id),
    onSuccess: () => {
      setDeleteConfirm(null)
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      toast.success('Пользователь удалён')
    },
    onError: () => toast.error('Не удалось удалить пользователя'),
  })

  const resetPasswordMutation = useMutation({
    mutationFn: (id: string) => authApi.resetPassword(id),
    onSuccess: (res) => {
      setResetPasswordId(null)
      setNewPassword(res.new_password)
      toast.success('Пароль сброшен')
    },
    onError: () => toast.error('Не удалось сбросить пароль'),
  })

  const saveEditMutation = useMutation({
    mutationFn: () => {
      if (!editUser) return Promise.reject()
      return authApi.updateUser(editUser.id, {
        full_name: editFullName || undefined,
        phone: editPhone || undefined,
        role: editRole,
        district_id: editRole !== 'admin' ? (editDistrictId || undefined) : undefined,
      })
    },
    onSuccess: () => {
      setEditUser(null)
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      toast.success('Изменения сохранены')
    },
    onError: () => toast.error('Не удалось сохранить изменения'),
  })

  const openEdit = (u: UserAdminOut) => {
    setEditUser(u)
    setEditFullName(u.full_name)
    setEditPhone(u.phone ?? '')
    setEditRole(u.role as Role)
    setEditDistrictId(u.district_id ?? '')
  }

  const inviteLink = lastInvite ? `${window.location.origin}/register/${lastInvite.token}` : null

  const copyLink = async () => {
    if (!inviteLink) return
    await navigator.clipboard.writeText(inviteLink)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="h-full flex flex-col">
      <div className="bg-primary-800 text-white px-4 py-3 flex items-center gap-3 shrink-0">
        <button onClick={() => navigate('/')} className="p-1 rounded-lg hover:bg-primary-700">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <h1 className="text-lg font-bold">Пользователи</h1>
        {users && (
          <span className="text-xs text-blue-200 ml-auto">{users.length} чел.</span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Поиск */}
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            className="input-field pl-9 text-sm"
            placeholder="Поиск по ФИО, логину, телефону, району..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <button
          onClick={() => { setShowInviteForm((v) => !v); setLastInvite(null) }}
          className="btn-primary flex items-center gap-2"
        >
          <UserPlus className="w-4 h-4" /> Пригласить пользователя
        </button>

        {showInviteForm && (
          <form
            onSubmit={(e) => { e.preventDefault(); inviteMutation.mutate() }}
            className="card space-y-3"
          >
            <div>
              <label className="label" htmlFor="login">Логин</label>
              <input
                id="login" className="input-field" value={login}
                onChange={(e) => setLogin(e.target.value)} required minLength={3}
              />
            </div>
            <div>
              <label className="label" htmlFor="full_name">ФИО</label>
              <input
                id="full_name" className="input-field" value={fullName}
                onChange={(e) => setFullName(e.target.value)} required
              />
            </div>
            <div>
              <label className="label" htmlFor="role">Роль</label>
              <select
                id="role" className="input-field" value={role}
                onChange={(e) => setRole(e.target.value as Role)}
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>{ROLE_LABELS[r]}</option>
                ))}
              </select>
            </div>
            {role !== 'admin' && (
              <div>
                <label className="label" htmlFor="district">
                  Район {role === 'reviewer' && '(не выбран — весь округ)'}
                </label>
                <select
                  id="district" className="input-field" value={districtId}
                  onChange={(e) => setDistrictId(e.target.value)}
                >
                  <option value="">—</option>
                  {districts?.map((d) => (
                    <option key={d.id} value={d.id}>{d.name}</option>
                  ))}
                </select>
              </div>
            )}
            <button type="submit" disabled={inviteMutation.isPending} className="btn-primary w-full">
              {inviteMutation.isPending ? 'Создаём…' : 'Создать приглашение'}
            </button>
          </form>
        )}

        {inviteLink && (
          <div className="card bg-green-50 border-green-200">
            <p className="text-sm text-gray-700 mb-2">
              Ссылка для регистрации ({lastInvite!.full_name}) — действует 72 часа:
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 text-xs bg-white rounded-lg px-2 py-2 border border-gray-200 break-all">
                {inviteLink}
              </code>
              <button onClick={copyLink} className="btn-outline shrink-0 p-2" title="Скопировать">
                {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
              </button>
            </div>
          </div>
        )}

        {/* Сброшенный пароль — показываем один раз */}
        {newPassword && (
          <div className="card bg-yellow-50 border-yellow-200">
            <p className="text-sm text-gray-700 mb-1">Новый пароль — передайте пользователю лично:</p>
            <div className="flex items-center gap-2">
              <code className="flex-1 text-sm font-bold bg-white rounded-lg px-3 py-2 border border-yellow-300">
                {newPassword}
              </code>
              <button
                onClick={() => { navigator.clipboard.writeText(newPassword); toast.success('Скопировано') }}
                className="btn-outline shrink-0 p-2"
              >
                <Copy className="w-4 h-4" />
              </button>
              <button onClick={() => setNewPassword(null)} className="btn-outline shrink-0 p-2">
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* Таблица пользователей */}
        <div className="card p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-left">
              <tr>
                <th className="px-4 py-2 font-medium">ФИО</th>
                <th className="px-4 py-2 font-medium">Логин</th>
                <th className="px-4 py-2 font-medium">Роль</th>
                <th className="px-4 py-2 font-medium hidden md:table-cell">Район</th>
                <th className="px-4 py-2 font-medium hidden md:table-cell">Телефон</th>
                <th className="px-4 py-2 font-medium">Статус</th>
                <th className="px-4 py-2 font-medium w-10"></th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers?.map((u) => (
                <tr key={u.id} className="border-t border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-2 font-medium">{u.full_name}</td>
                  <td className="px-4 py-2 text-gray-500">{u.login}</td>
                  <td className="px-4 py-2">
                    <span className="badge badge-pending">{ROLE_LABELS[u.role as Role] ?? u.role}</span>
                  </td>
                  <td className="px-4 py-2 text-gray-500 hidden md:table-cell">
                    {u.role !== 'admin' ? districtName(u.district_id) : '—'}
                  </td>
                  <td className="px-4 py-2 text-gray-500 hidden md:table-cell">
                    {u.phone ?? '—'}
                  </td>
                  <td className="px-4 py-2">
                    <button
                      onClick={() => toggleActiveMutation.mutate({ id: u.id, is_active: !u.is_active })}
                      className={`badge text-xs ${u.is_active ? 'badge-ok' : 'badge-nok'}`}
                    >
                      {u.is_active ? 'активен' : 'отключён'}
                    </button>
                  </td>
                  <td className="px-2 py-2">
                    <div className="flex gap-0.5">
                      <button
                        onClick={() => openEdit(u)}
                        className="p-1.5 rounded hover:bg-gray-200 text-gray-500"
                        title="Редактировать"
                      >
                        <Edit3 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => setResetPasswordId(u.id)}
                        className="p-1.5 rounded hover:bg-gray-200 text-gray-500"
                        title="Сбросить пароль"
                      >
                        <Key className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => setDeleteConfirm(u.id)}
                        className="p-1.5 rounded hover:bg-red-100 text-gray-500 hover:text-red-600"
                        title="Удалить"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {filteredUsers?.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                    {searchQuery ? 'Ничего не найдено' : 'Нет пользователей'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Модалка подтверждения удаления */}
      {deleteConfirm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl p-6 max-w-sm w-full shadow-xl">
            <h3 className="font-bold text-lg mb-2">Удалить пользователя?</h3>
            <p className="text-sm text-gray-600 mb-4">
              Это действие необратимо. Все обходы и замечания пользователя останутся, но он больше не сможет войти.
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="btn-outline flex-1 py-2"
              >
                Отмена
              </button>
              <button
                onClick={() => deleteMutation.mutate(deleteConfirm)}
                disabled={deleteMutation.isPending}
                className="flex-1 py-2 bg-red-600 text-white rounded-lg font-medium hover:bg-red-700"
              >
                {deleteMutation.isPending ? 'Удаляю...' : 'Удалить'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Модалка подтверждения сброса пароля */}
      {resetPasswordId && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl p-6 max-w-sm w-full shadow-xl">
            <h3 className="font-bold text-lg mb-2">Сбросить пароль?</h3>
            <p className="text-sm text-gray-600 mb-4">
              Будет сгенерирован новый случайный пароль. Передайте его пользователю лично.
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setResetPasswordId(null)}
                className="btn-outline flex-1 py-2"
              >
                Отмена
              </button>
              <button
                onClick={() => resetPasswordMutation.mutate(resetPasswordId)}
                disabled={resetPasswordMutation.isPending}
                className="flex-1 py-2 bg-amber-600 text-white rounded-lg font-medium hover:bg-amber-700"
              >
                {resetPasswordMutation.isPending ? 'Сброс...' : 'Сбросить'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Модалка редактирования */}
      {editUser && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl p-6 max-w-sm w-full shadow-xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-lg">Редактирование</h3>
              <button onClick={() => setEditUser(null)} className="p-1 hover:bg-gray-100 rounded-lg">
                <X className="w-5 h-5 text-gray-400" />
              </button>
            </div>

            <div className="text-sm text-gray-500 mb-4">Логин: {editUser.login}</div>

            <div className="space-y-3">
              <div>
                <label className="label">ФИО</label>
                <input
                  className="input-field text-sm"
                  value={editFullName}
                  onChange={(e) => setEditFullName(e.target.value)}
                />
              </div>
              <div>
                <label className="label">Телефон</label>
                <input
                  className="input-field text-sm"
                  value={editPhone}
                  onChange={(e) => setEditPhone(e.target.value)}
                  placeholder="+7 ..."
                />
              </div>
              <div>
                <label className="label">Роль</label>
                <select
                  className="input-field text-sm"
                  value={editRole}
                  onChange={(e) => setEditRole(e.target.value as Role)}
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>{ROLE_LABELS[r]}</option>
                  ))}
                </select>
              </div>
              {editRole !== 'admin' && (
                <div>
                  <label className="label">
                    Район {editRole === 'reviewer' && '(не выбран — весь округ)'}
                  </label>
                  <select
                    className="input-field text-sm"
                    value={editDistrictId}
                    onChange={(e) => setEditDistrictId(e.target.value)}
                  >
                    <option value="">—</option>
                    {districts?.map((d) => (
                      <option key={d.id} value={d.id}>{d.name}</option>
                    ))}
                  </select>
                </div>
              )}
              <button
                onClick={() => saveEditMutation.mutate()}
                disabled={saveEditMutation.isPending}
                className="btn-primary w-full py-2"
              >
                {saveEditMutation.isPending ? 'Сохранение...' : 'Сохранить'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
