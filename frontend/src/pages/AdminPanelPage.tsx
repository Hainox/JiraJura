import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Users, Clock, KeyRound, MapPinned, AlertCircle, ClipboardCheck, ShieldCheck, BarChart3, Clapperboard, Wrench, MessageSquareWarning } from 'lucide-react'
import { useDemoModeStore } from '@/stores/demoMode'
import { useAuthStore } from '@/stores/auth'

const DEV_SECTIONS = [
  { to: '/admin/system', icon: Wrench, title: 'Разработчик', desc: 'Статус БД, хранилища, окружения — эксплуатационная сводка' },
]

const REVIEW_SECTIONS = [
  { to: '/admin/reviews', icon: ClipboardCheck, title: 'Приёмка обходов', desc: 'Обходы, ожидающие проверки и приёмки' },
  { to: '/admin/control', icon: ShieldCheck, title: 'Финальный контроль', desc: 'Исправленные замечания: принять и закрыть или вернуть на доработку' },
  { to: '/admin/issues', icon: AlertCircle, title: 'Замечания', desc: 'Все замечания округа, назначение, приёмка исправлений' },
  { to: '/admin/dashboard', icon: BarChart3, title: 'Дашборд', desc: 'Сводка по округу, выгрузка в Excel' },
  { to: '/admin/feedback', icon: MessageSquareWarning, title: 'Обращения', desc: 'Жалобы с публичной формы /feedback — очередь на разбор' },
]

const SECTIONS = [
  { to: '/admin/users', icon: Users, title: 'Пользователи', desc: 'Приглашения, роли, районы, сброс паролей' },
  { to: '/admin/sites', icon: MapPinned, title: 'Районы и площадки', desc: 'Переименование/объединение районов, дворы, площадки' },
  { to: '/admin/audit', icon: Clock, title: 'Журнал аудита', desc: 'Кто и что менял в системе' },
  { to: '/admin/login-history', icon: KeyRound, title: 'История входов', desc: 'Успешные и неудачные попытки входа по логину и IP' },
]

export default function AdminPanelPage() {
  const navigate = useNavigate()
  const demoMode = useDemoModeStore((s) => s.enabled)
  const toggleDemoMode = useDemoModeStore((s) => s.toggle)
  const isDeveloper = useAuthStore((s) => s.user?.is_developer)

  return (
    <div className="h-full flex flex-col bg-gray-50">
      <div className="bg-primary-800 text-white px-4 py-3 flex items-center gap-3 shrink-0">
        <button onClick={() => navigate('/')} data-prefetch="/" className="p-1 -ml-1 hover:bg-primary-700 rounded-lg">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <h1 className="font-bold text-lg">Админ-панель</h1>
          <p className="text-blue-200 text-xs">Разделы, доступные только администратору</p>
        </div>
      </div>

      <div className="overflow-y-auto flex-1 p-4 space-y-5">
        <button
          onClick={toggleDemoMode}
          className={`w-full flex items-center gap-3 rounded-xl px-4 py-3 text-left transition-colors ${
            demoMode ? 'bg-amber-500 text-amber-950' : 'bg-white border border-gray-200 text-gray-700 hover:border-amber-300'
          }`}
        >
          <Clapperboard className="w-5 h-5 shrink-0" />
          <div className="min-w-0 flex-1">
            <div className="font-semibold">Демо-режим {demoMode ? 'включён' : 'выключен'}</div>
            <div className={`text-xs mt-0.5 ${demoMode ? 'text-amber-900' : 'text-gray-500'}`}>
              Для показа руководству — принятие обходов и изменение статусов замечаний не сохраняются
            </div>
          </div>
        </button>
        <div>
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2 px-1">Замечания и приёмка</h2>
          <div className="space-y-3">
            {REVIEW_SECTIONS.map(({ to, icon: Icon, title, desc }) => (
              <button
                key={to}
                onClick={() => navigate(to)} data-prefetch={to}
                className="card w-full text-left flex items-center gap-3 hover:border-primary-300 transition-colors"
              >
                <div className="w-11 h-11 rounded-xl bg-amber-50 text-amber-700 flex items-center justify-center shrink-0">
                  <Icon className="w-5 h-5" />
                </div>
                <div className="min-w-0">
                  <div className="font-semibold text-gray-800">{title}</div>
                  <div className="text-xs text-gray-500 mt-0.5">{desc}</div>
                </div>
              </button>
            ))}
          </div>
        </div>

        <div>
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2 px-1">Управление</h2>
          <div className="space-y-3">
            {SECTIONS.map(({ to, icon: Icon, title, desc }) => (
              <button
                key={to}
                onClick={() => navigate(to)} data-prefetch={to}
                className="card w-full text-left flex items-center gap-3 hover:border-primary-300 transition-colors"
              >
                <div className="w-11 h-11 rounded-xl bg-primary-50 text-primary-700 flex items-center justify-center shrink-0">
                  <Icon className="w-5 h-5" />
                </div>
                <div className="min-w-0">
                  <div className="font-semibold text-gray-800">{title}</div>
                  <div className="text-xs text-gray-500 mt-0.5">{desc}</div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {isDeveloper && (
          <div>
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2 px-1">Разработчик</h2>
            <div className="space-y-3">
              {DEV_SECTIONS.map(({ to, icon: Icon, title, desc }) => (
                <button
                  key={to}
                  onClick={() => navigate(to)} data-prefetch={to}
                  className="card w-full text-left flex items-center gap-3 hover:border-primary-300 transition-colors"
                >
                  <div className="w-11 h-11 rounded-xl bg-gray-100 text-gray-600 flex items-center justify-center shrink-0">
                    <Icon className="w-5 h-5" />
                  </div>
                  <div className="min-w-0">
                    <div className="font-semibold text-gray-800">{title}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{desc}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
