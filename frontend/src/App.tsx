import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth'
import LoginPage from '@/pages/LoginPage'
import MapPage from '@/pages/MapPage'
import SiteDetailPage from '@/pages/SiteDetailPage'
import InspectionPage from '@/pages/InspectionPage'
import SummaryPage from '@/pages/SummaryPage'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuth = useAuthStore((s) => s.isAuthenticated)
  return isAuth ? <>{children}</> : <Navigate to="/login" replace />
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
