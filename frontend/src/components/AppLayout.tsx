import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth'
import { useTheme } from '@/lib/theme'
import {
  ArrowLeft, LogOut, UserCircle, Sun, Moon,
  BarChart3, AlertCircle, Clock, Users, Download,
} from 'lucide-react'
import { reportsApi } from '@/lib/api'
import { notify as toast } from '@/lib/toast'

interface AppLayoutProps {
  title: string
  subtitle?: string
  backTo?: string
  children: React.ReactNode
  /** Кнопки в правой части шапки */
  actions?: React.ReactNode
}

export function AppLayout({ title, subtitle, backTo = '/', children, actions }: AppLayoutProps) {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const logoutStore = useAuthStore((s) => s.logout)
  const { theme, toggleTheme } = useTheme()

  const isAdmin = user?.role === 'admin'
  const isReviewerLike = user?.role === 'reviewer' || isAdmin

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="bg-primary-800 text-white px-4 py-3 shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(backTo)}
            className="p-1.5 rounded-lg hover:bg-primary-700 transition-colors shrink-0"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="font-bold text-lg truncate">{title}</h1>
            {subtitle && <p className="text-blue-200 text-xs truncate">{subtitle}</p>}
          </div>

          {/* Actions slot */}
          {actions && <div className="flex items-center gap-1">{actions}</div>}

          {/* Стандартные кнопки — только если нет кастомных actions (используется на MapPage) */}
          {!actions && (
            <div className="flex gap-1">
              {user?.role !== 'inspector' && (
                <>
                  <button onClick={() => navigate('/dashboard')} className="p-2 rounded-lg hover:bg-primary-700 transition-colors" title="Дашборд">
                    <BarChart3 className="w-5 h-5" />
                  </button>
                  <button onClick={() => navigate('/issues')} className="p-2 rounded-lg hover:bg-primary-700 transition-colors" title="Замечания">
                    <AlertCircle className="w-5 h-5" />
                  </button>
                </>
              )}
              {isAdmin && (
                <>
                  <button onClick={() => navigate('/admin/audit')} className="p-2 rounded-lg hover:bg-primary-700 transition-colors" title="Аудит">
                    <Clock className="w-5 h-5" />
                  </button>
                  <button onClick={() => navigate('/admin/users')} className="p-2 rounded-lg hover:bg-primary-700 transition-colors" title="Пользователи">
                    <Users className="w-5 h-5" />
                  </button>
                </>
              )}
              {isReviewerLike && (
                <button onClick={() => toast.promise(reportsApi.exportXlsx(), {
                  loading: 'Готовлю файл...', success: 'Файл скачан', error: 'Ошибка выгрузки',
                })} className="p-2 rounded-lg hover:bg-primary-700 transition-colors" title="Выгрузка в Excel">
                  <Download className="w-5 h-5" />
                </button>
              )}
              <button onClick={toggleTheme} className="p-2 rounded-lg hover:bg-primary-700 transition-colors" title={theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}>
                {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
              </button>
              <button onClick={() => navigate('/profile')} className="p-2 rounded-lg hover:bg-primary-700 transition-colors" title="Профиль">
                <UserCircle className="w-5 h-5" />
              </button>
              <button onClick={() => { logoutStore(); navigate('/login') }} className="p-2 rounded-lg hover:bg-primary-700 transition-colors" title="Выйти">
                <LogOut className="w-5 h-5" />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">{children}</div>
    </div>
  )
}
