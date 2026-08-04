import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { authApi, districtsApi } from '@/lib/api'
import { ROLES, ROLE_LABELS } from '@/lib/roles'
import type { Role, UserInviteCreated } from '@/types'
import toast from 'react-hot-toast'
import { ArrowLeft, UserPlus, Copy, Check } from 'lucide-react'

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

  const { data: users } = useQuery({ queryKey: ['admin-users'], queryFn: authApi.listUsers })
  const { data: districts } = useQuery({ queryKey: ['districts'], queryFn: districtsApi.list })

  const districtName = (id?: string) => districts?.find((d) => d.id === id)?.name ?? '—'

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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
    },
    onError: () => toast.error('Не удалось изменить статус пользователя'),
  })

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
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
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
              Ссылка для регистрации ({lastInvite!.full_name}) — действует 72 часа, передайте её человеку лично:
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

        <div className="card p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-left">
              <tr>
                <th className="px-4 py-2 font-medium">ФИО</th>
                <th className="px-4 py-2 font-medium">Логин</th>
                <th className="px-4 py-2 font-medium">Роль</th>
                <th className="px-4 py-2 font-medium">Район</th>
                <th className="px-4 py-2 font-medium">Статус</th>
              </tr>
            </thead>
            <tbody>
              {users?.map((u) => (
                <tr key={u.id} className="border-t border-gray-100">
                  <td className="px-4 py-2">{u.full_name}</td>
                  <td className="px-4 py-2 text-gray-500">{u.login}</td>
                  <td className="px-4 py-2">
                    <span className="badge badge-pending">{ROLE_LABELS[u.role as Role] ?? u.role}</span>
                  </td>
                  <td className="px-4 py-2 text-gray-500">
                    {u.role === 'inspector' || u.role === 'reviewer' ? districtName(u.district_id) : '—'}
                  </td>
                  <td className="px-4 py-2">
                    <button
                      onClick={() => toggleActiveMutation.mutate({ id: u.id, is_active: !u.is_active })}
                      className={`badge ${u.is_active ? 'badge-ok' : 'badge-nok'}`}
                    >
                      {u.is_active ? 'активен' : 'отключён'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
