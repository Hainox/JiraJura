import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/lib/api'
import type { Role } from '@/types'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import LoginPage from '@/pages/LoginPage'
import RegisterPage from '@/pages/RegisterPage'
import ChangePasswordPage from '@/pages/ChangePasswordPage'
import MapPage from '@/pages/MapPage'
import SiteDetailPage from '@/pages/SiteDetailPage'
import InspectionPage from '@/pages/InspectionPage'
import SummaryPage from '@/pages/SummaryPage'
import AdminUsersPage from '@/pages/AdminUsersPage'
import IssuesPage from '@/pages/IssuesPage'
import IssueFixPage from '@/pages/IssueFixPage'
import ProfilePage from '@/pages/ProfilePage'
import AuditPage from '@/pages/AuditPage'
import DashboardPage from '@/pages/DashboardPage'
import MyInspectionsPage from '@/pages/MyInspectionsPage'

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
    staleTime: 5 * 60 * 1000,
  })
  useEffect(() => {
    if (data) setUser(data)
  }, [data, setUser])
}

export default function App() {
  useSyncUserFromServer()
  return (
    <ErrorBoundary>
      <div className="h-full flex flex-col bg-gray-50">
        <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register/:token" element={<RegisterPage />} />
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
            <ProtectedRoute roles={['reviewer', 'admin']}>
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
            <ProtectedRoute roles={['reviewer', 'admin']}>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/issues/:id"
          element={
            <ProtectedRoute roles={['reviewer', 'admin']}>
              <IssueFixPage />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
    </ErrorBoundary>
  )
}
