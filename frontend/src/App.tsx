import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth'
import type { Role } from '@/types'
import LoginPage from '@/pages/LoginPage'
import RegisterPage from '@/pages/RegisterPage'
import MapPage from '@/pages/MapPage'
import SiteDetailPage from '@/pages/SiteDetailPage'
import InspectionPage from '@/pages/InspectionPage'
import SummaryPage from '@/pages/SummaryPage'
import AdminUsersPage from '@/pages/AdminUsersPage'

function ProtectedRoute({ children, roles }: { children: React.ReactNode; roles?: Role[] }) {
  const isAuth = useAuthStore((s) => s.isAuthenticated)
  const userRole = useAuthStore((s) => s.user?.role)
  if (!isAuth) return <Navigate to="/login" replace />
  if (roles && !roles.includes(userRole as Role)) return <Navigate to="/" replace />
  return <>{children}</>
}

export default function App() {
  const hydrate = useAuthStore((s) => s.hydrate)

  useEffect(() => {
    hydrate()
  }, [hydrate])

  return (
    <div className="h-full flex flex-col bg-gray-50">
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register/:token" element={<RegisterPage />} />
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
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  )
}
