# Page dependency trees

## /dashboard and /admin/dashboard

Entry: `frontend/src/pages/DashboardPage.tsx`

Dependencies:
- `frontend/src/lib/api.ts` — statistics, districts, reports API calls
- `frontend/src/lib/statistics.ts` — period helpers and percentage colours
- `frontend/src/types/index.ts` — `StatsDistrictRow`
- `frontend/src/stores/auth.ts` — district scope and role
- `frontend/src/lib/toast.ts` — export feedback
- `frontend/src/index.css` — global font and shared utility styles

Render structure: blue header → period/filter toolbar → tab strip → overview or data table. The target change belongs in the `Обходы` table and overview KPI while `Устранение` remains a separate workflow table.
