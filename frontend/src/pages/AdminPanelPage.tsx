import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Users, Clock, MapPinned, ClipboardList, AlertCircle, ClipboardCheck, BarChart3 } from 'lucide-react'

const REVIEW_SECTIONS = [
  { to: '/admin/reviews', icon: ClipboardCheck, title: 'Приёмка обходов', desc: 'Обходы, ожидающие проверки и приёмки' },
  { to: '/admin/issues', icon: AlertCircle, title: 'Замечания', desc: 'Все замечания округа, назначение, приёмка исправлений' },
  { to: '/admin/dashboard', icon: BarChart3, title: 'Дашборд', desc: 'Сводка по округу, выгрузка в Excel' },
]

const SECTIONS = [
  { to: '/admin/users', icon: Users, title: 'Пользователи', desc: 'Приглашения, роли, районы, сброс паролей' },
  { to: '/admin/sites', icon: MapPinned, title: 'Районы и площадки', desc: 'Переименование/объединение районов, дворы, площадки' },
  { to: '/admin/checklists', icon: ClipboardList, title: 'Чек-листы', desc: 'Пункты чек-листа для детских и спортивных площадок' },
  { to: '/admin/audit', icon: Clock, title: 'Журнал аудита', desc: 'Кто и что менял в системе' },
]

export default function AdminPanelPage() {
  const navigate = useNavigate()

  return (
    <div className="h-full flex flex-col bg-gray-50">
      <div className="bg-primary-800 text-white px-4 py-3 flex items-center gap-3 shrink-0">
        <button onClick={() => navigate('/')} className="p-1 -ml-1 hover:bg-primary-700 rounded-lg">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <h1 className="font-bold text-lg">Админ-панель</h1>
          <p className="text-blue-200 text-xs">Разделы, доступные только администратору</p>
        </div>
      </div>

      <div className="overflow-y-auto flex-1 p-4 space-y-5">
        <div>
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2 px-1">Замечания и приёмка</h2>
          <div className="space-y-3">
            {REVIEW_SECTIONS.map(({ to, icon: Icon, title, desc }) => (
              <button
                key={to}
                onClick={() => navigate(to)}
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
                onClick={() => navigate(to)}
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
      </div>
    </div>
  )
}
