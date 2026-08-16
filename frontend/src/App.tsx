import { lazy, Suspense, useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from '@/stores/auth'
import { useDemoModeStore } from '@/stores/demoMode'
import { authApi } from '@/lib/api'
import type { Role } from '@/types'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import RoutePrefetcher from '@/components/RoutePrefetcher'
import { routeLoaders } from '@/lib/routePreload'

// Страницы грузятся лениво: каждый роут — отдельный JS-чанк, который Vite
// отдаёт только при первом переходе. Первый экран (логин) и главный бандл
// сильно худеют; тяжёлая карта (leaflet) уезжает в свой чанк и не
// загружается, пока пользователь не открыл карту. Все чанки прекэшируются
// service worker'ом при первой установке PWA (globPatterns в vite.config.ts),
// поэтому офлайн-режим после первого запуска не страдает.
const LoginPage = lazy(routeLoaders['/login'])
const RegisterPage = lazy(routeLoaders['/register/:token'])
const FeedbackFormPage = lazy(routeLoaders['/feedback'])
const AdminFeedbackPage = lazy(routeLoaders['/admin/feedback'])
const ChangePasswordPage = lazy(routeLoaders['/change-password'])
const MapPage = lazy(routeLoaders['/'])
const SiteDetailPage = lazy(routeLoaders['/sites/:id'])
const InspectionPage = lazy(routeLoaders['/inspections/:id'])
const SummaryPage = lazy(routeLoaders['/inspections/:id/summary'])
const AdminUsersPage = lazy(routeLoaders['/admin/users'])
const IssuesPage = lazy(routeLoaders['/issues'])
const IssueFixPage = lazy(routeLoaders['/issues/:id'])
const ProfilePage = lazy(routeLoaders['/profile'])
const AuditPage = lazy(routeLoaders['/admin/audit'])
const DashboardPage = lazy(routeLoaders['/dashboard'])
const MyInspectionsPage = lazy(routeLoaders['/my-inspections'])
const AdminPanelPage = lazy(routeLoaders['/admin'])
const AdminSitesPage = lazy(routeLoaders['/admin/sites'])
const AdminChecklistsPage = lazy(routeLoaders['/admin/checklists'])
const AdminReviewsPage = lazy(routeLoaders['/admin/reviews'])
const AdminIssueControlPage = lazy(routeLoaders['/admin/control'])
const AdminSystemPage = lazy(routeLoaders['/admin/system'])

// Пока чанк страницы скачивается, показываем аккуратный спиннер вместо
// пустого экрана. flex-1 — растягивается на оставшуюся высоту под
// баннером демо-режима.
function PageFallback() {
  return (
    <div className="flex-1 flex items-center justify-center bg-gray-50">
      <div className="flex flex-col items-center gap-3 text-gray-400">
        <div className="w-8 h-8 border-2 border-gray-300 border-t-primary-600 rounded-full animate-spin" />
        <span className="text-sm">Загрузка…</span>
      </div>
    </div>
  )
}

function ProtectedRoute({ children, roles }: { children: React.ReactNode; roles?: Role[] }) {
  const isAuth = useAuthStore((s) => s.isAuthenticated)
  const userRole = useAuthStore((s) => s.user?.role)
  if (!isAuth) return <Navigate to="/login" replace />
  // Не редиректим force_pw_change когда уже на странице смены пароля
  if (localStorage.getItem('force_pw_change') === '1' && window.location.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />
  }
  if (roles && !roles.includes(userRole as Role)) return <Navigate to="/" replace />
  return <>{children}</>
}

// Роль/район/ФИО и т.п. приходят в localStorage один раз при входе и
// иначе никогда не обновляются — если админ поменял пользователю район
// или роль, пока тот уже залогинен, сессия молча продолжает работать по
// старым данным (в проде так у инспектора с назначенным районом
// в базе на карте была пустая площадка/"Район не назначен", пока он не
// перелогинился вручную). Подтягиваем актуальные данные с сервера при
// каждом возврате в приложение — refetchOnWindowFocus у react-query как
// раз покрывает случай "открыл вкладку после того как админ что-то поменял".
function useSyncUserFromServer() {
  const isAuth = useAuthStore((s) => s.isAuthenticated)
  const setUser = useAuthStore((s) => s.setUser)
  const { data } = useQuery({
    queryKey: ['auth-me'],
    queryFn: authApi.me,
    enabled: isAuth,
    // Район/роль — права доступа, а не обычный справочник. После изменения
    // администратором клиент должен получить их при каждом открытии/возврате
    // во вкладку, иначе UI продолжает показывать старый район до перелогина.
    // Глобальный defaultOptions в main.tsx ставит refetchOnWindowFocus=false,
    // поэтому оба флага включаем явно и не кэшируем меш (staleTime: 0).
    staleTime: 0,
    refetchOnMount: 'always',
    refetchOnWindowFocus: 'always',
  })
  useEffect(() => {
    if (data) setUser(data)
  }, [data, setUser])
}

export default function App() {
  useSyncUserFromServer()
  const demoMode = useDemoModeStore((s) => s.enabled)
  return (
    <ErrorBoundary>
      <RoutePrefetcher />
      <div className="h-full flex flex-col bg-gray-50">
        {demoMode && (
          <div className="bg-amber-500 text-amber-950 text-xs font-semibold text-center py-1 shrink-0">
            🎬 Демо-режим — изменения не сохраняются
          </div>
        )}
        <Suspense fallback={<PageFallback />}>
        <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register/:token" element={<RegisterPage />} />
        <Route path="/feedback" element={<FeedbackFormPage />} />
        <Route
          path="/admin/feedback"
          element={
            <ProtectedRoute roles={['admin']}>
              <AdminFeedbackPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/change-password"
          element={
            <ProtectedRoute>
              <ChangePasswordPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/users"
          element={
            <ProtectedRoute roles={['admin']}>
              <AdminUsersPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin"
          element={
            <ProtectedRoute roles={['admin']}>
              <AdminPanelPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/sites"
          element={
            <ProtectedRoute roles={['admin']}>
              <AdminSitesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/checklists"
          element={
            <ProtectedRoute roles={['admin']}>
              <AdminChecklistsPage />
            </ProtectedRoute>
          }
        />
        {/* Отдельное меню админа для замечаний/приёмки — те же компоненты,
            что и у reviewer, они сами определяют "домашний" роут по роли
            (см. isAdmin/basePath внутри), но смонтированы отдельно, чтобы
            админ никогда не задевал roles={['reviewer']} ниже. */}
        <Route
          path="/admin/issues"
          element={
            <ProtectedRoute roles={['admin']}>
              <IssuesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/issues/:id"
          element={
            <ProtectedRoute roles={['admin']}>
              <IssueFixPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/dashboard"
          element={
            <ProtectedRoute roles={['admin']}>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/reviews"
          element={
            <ProtectedRoute roles={['admin']}>
              <AdminReviewsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/control"
          element={
            <ProtectedRoute roles={['admin']}>
              <AdminIssueControlPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/system"
          element={
            <ProtectedRoute roles={['admin']}>
              <AdminSystemPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <MapPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/sites/:id"
          element={
            <ProtectedRoute>
              <SiteDetailPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/inspections/:id"
          element={
            <ProtectedRoute>
              <InspectionPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/inspections/:id/summary"
          element={
            <ProtectedRoute>
              <SummaryPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/issues"
          element={
            <ProtectedRoute roles={['reviewer']}>
              <IssuesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/profile"
          element={
            <ProtectedRoute>
              <ProfilePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/my-inspections"
          element={
            <ProtectedRoute roles={['inspector']}>
              <MyInspectionsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/audit"
          element={
            <ProtectedRoute roles={['admin']}>
              <AuditPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute roles={['reviewer']}>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/issues/:id"
          element={
            <ProtectedRoute roles={['reviewer']}>
              <IssueFixPage />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </Suspense>
    </div>
    </ErrorBoundary>
  )
}
