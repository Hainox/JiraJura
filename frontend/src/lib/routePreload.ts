import type { ComponentType } from 'react'

export type RouteLoader = () => Promise<{ default: ComponentType }>

// Единый реестр ленивых чанков маршрутов. App.tsx берёт отсюда те же
// loaders для React.lazy, а RoutePrefetcher — для префетча по hover/focus.
// Bundler дедуплицирует динамический import одного модуля в один чанк,
// поэтому префетч и реальный переход качают файл ровно один раз.
const routes: Array<{ pattern: string; load: RouteLoader }> = [
  { pattern: '/', load: () => import('@/pages/MapPage') },
  { pattern: '/login', load: () => import('@/pages/LoginPage') },
  { pattern: '/register/:token', load: () => import('@/pages/RegisterPage') },
  { pattern: '/feedback', load: () => import('@/pages/FeedbackFormPage') },
  { pattern: '/change-password', load: () => import('@/pages/ChangePasswordPage') },
  { pattern: '/sites/:id', load: () => import('@/pages/SiteDetailPage') },
  { pattern: '/inspections/:id', load: () => import('@/pages/InspectionPage') },
  { pattern: '/inspections/:id/summary', load: () => import('@/pages/SummaryPage') },
  { pattern: '/my-inspections', load: () => import('@/pages/MyInspectionsPage') },
  { pattern: '/issues', load: () => import('@/pages/IssuesPage') },
  { pattern: '/issues/:id', load: () => import('@/pages/IssueFixPage') },
  { pattern: '/dashboard', load: () => import('@/pages/DashboardPage') },
  { pattern: '/profile', load: () => import('@/pages/ProfilePage') },
  { pattern: '/admin', load: () => import('@/pages/AdminPanelPage') },
  { pattern: '/admin/users', load: () => import('@/pages/AdminUsersPage') },
  { pattern: '/admin/sites', load: () => import('@/pages/AdminSitesPage') },
  { pattern: '/admin/checklists', load: () => import('@/pages/AdminChecklistsPage') },
  { pattern: '/admin/reviews', load: () => import('@/pages/AdminReviewsPage') },
  { pattern: '/admin/control', load: () => import('@/pages/AdminIssueControlPage') },
  { pattern: '/admin/issues', load: () => import('@/pages/IssuesPage') },
  { pattern: '/admin/issues/:id', load: () => import('@/pages/IssueFixPage') },
  { pattern: '/admin/dashboard', load: () => import('@/pages/DashboardPage') },
  { pattern: '/admin/feedback', load: () => import('@/pages/AdminFeedbackPage') },
  { pattern: '/admin/audit', load: () => import('@/pages/AuditPage') },
  { pattern: '/admin/system', load: () => import('@/pages/AdminSystemPage') },
]

export const routeLoaders: Record<string, RouteLoader> = Object.fromEntries(
  routes.map((r) => [r.pattern, r.load]),
)

// Один чанк достаточно префетчить один раз за сессию: import() кэшируется
// браузером, повторные вызовы не создают новых сетевых запросов.
const prefetched = new Set<string>()

function matches(pattern: string, path: string): boolean {
  const p = pattern.split('/').filter(Boolean)
  const q = path.split('/').filter(Boolean)
  if (p.length !== q.length) return false
  return p.every((seg, i) => seg.startsWith(':') || seg === q[i])
}

/** Запускает фоновую загрузку чанка для маршрута (по шаблону или конкретному
 * пути с id). Ошибки глотает намеренно: префетч — оптимизация, а реальную
 * ошибку покажет Suspense/ErrorBoundary при настоящем переходе. */
export function prefetchRoute(path: string): void {
  for (const { pattern, load } of routes) {
    if (matches(pattern, path)) {
      if (!prefetched.has(pattern)) {
        prefetched.add(pattern)
        load().catch(() => {})
      }
      return
    }
  }
}
