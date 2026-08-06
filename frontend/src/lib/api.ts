import axios from 'axios'
import type {
  LoginRequest,
  LoginResponse,
  DistrictOut,
  SiteOut,
  SiteListOut,
  ChecklistTemplateOut,
  InspectionOut,
  InspectionListOut,
  IssueOut,
  IssueCreate,
  IssueListOut,
  PhotoOut,
  UserOut,
  UserAdminOut,
  UserInviteCreate,
  UserInviteCreated,
  UserInvitePreview,
  UserRoleUpdate,
  SelfUpdateRequest,
  PasswordResetOut,
  DashboardOut,
} from '@/types'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api/v1',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000, // 30 секунд — без этого запрос может висеть бесконечно
})

// Авто-прокидывание токена
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Обработка 401 — разлогин (но не на страницах входа/смены пароля)
api.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error.response?.status === 401) {
      const path = window.location.pathname
      // На страницах логина и смены пароля 401 — ожидаемое поведение,
      // даём странице самой показать ошибку.
      if (path === '/login' || path === '/change-password') {
        return Promise.reject(error)
      }
      localStorage.removeItem('access_token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// ── Auth ──
export const authApi = {
  login: (data: LoginRequest) =>
    api.post<LoginResponse>('/auth/login', data).then((r) => r.data),

  createInvite: (data: UserInviteCreate) =>
    api.post<UserInviteCreated>('/auth/invites', data).then((r) => r.data),

  previewInvite: (token: string) =>
    api.get<UserInvitePreview>(`/auth/invites/${token}`).then((r) => r.data),

  completeInvite: (token: string, password: string) =>
    api.post<LoginResponse>(`/auth/invites/${token}/complete`, { password }).then((r) => r.data),

  updateMe: (data: SelfUpdateRequest) =>
    api.patch<UserOut>('/auth/me', data).then((r) => r.data),

  listUsers: () => api.get<UserAdminOut[]>('/auth/users').then((r) => r.data),

  updateUser: (id: string, data: UserRoleUpdate) =>
    api.patch<UserAdminOut>(`/auth/users/${id}`, data).then((r) => r.data),

  deleteUser: (id: string) =>
    api.delete(`/auth/users/${id}`).then((r) => r.data),

  resetPassword: (id: string) =>
    api.post<PasswordResetOut>(`/auth/users/${id}/reset-password`).then((r) => r.data),

  changePassword: (newPassword: string, currentPassword?: string) =>
    api.post<LoginResponse>('/auth/change-password', { new_password: newPassword, current_password: currentPassword }).then((r) => r.data),
}

// ── Districts ──
export const districtsApi = {
  list: () => api.get<DistrictOut[]>('/districts/').then((r) => r.data),
}

// ── Sites ──
export const sitesApi = {
  // параметр фильтра по типу в API называется `type` и принимает значение
  // enum'а site_type как есть: «Детская площадка» / «Спортивная площадка»
  list: (params?: { district_id?: string; type?: string; page_size?: number }) =>
    api.get<SiteListOut>('/sites/', { params }).then((r) => r.data),

  get: (id: string) => api.get<SiteOut>(`/sites/${id}`).then((r) => r.data),
}

// ── Checklists ──
export const checklistsApi = {
  template: (params?: { site_type?: string }) =>
    api.get<ChecklistTemplateOut[]>('/sites/templates/checklist', { params }).then((r) => r.data),
}

// ── Inspections ──
export const inspectionsApi = {
  create: (siteId: string) =>
    api.post<InspectionOut>('/inspections/', { site_id: siteId }).then((r) => r.data),

  get: (id: string) => api.get<InspectionOut>(`/inspections/${id}`).then((r) => r.data),

  list: (params?: { site_id?: string; status?: string; district_id?: string; page_size?: number }) =>
    api.get<InspectionListOut>('/inspections/', { params }).then((r) => r.data),

  update: (id: string, data: Record<string, unknown>) =>
    api.patch<InspectionOut>(`/inspections/${id}`, data).then((r) => r.data),

  uploadPhoto: (id: string, file: File, checklistAnswerId?: string) => {
    const form = new FormData()
    form.append('file', file)
    const params = checklistAnswerId ? `?checklist_answer_id=${checklistAnswerId}` : ''
    return api
      .post<PhotoOut>(`/inspections/${id}/photos${params}`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data)
  },
}

// ── Reports ──
export const reportsApi = {
  dashboard: (params?: { district_id?: string; date_from?: string; date_to?: string }) =>
    api.get<DashboardOut>('/reports/dashboard', { params }).then((r) => r.data),

  // Скачивание Excel-выгрузки: файл приходит blob'ом (нужен Authorization-
  // заголовок, поэтому обычная ссылка <a href> не подходит) и отдаётся
  // пользователю через временный object URL.
  exportXlsx: async (params?: { district_id?: string; date_from?: string; date_to?: string }) => {
    const res = await api.get('/reports/export.xlsx', { params, responseType: 'blob' })
    const url = URL.createObjectURL(res.data as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `журнал_обходов_${new Date().toISOString().slice(0, 10)}.xlsx`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },

  // Тот же принцип, что и exportXlsx: /reports/pdf/{id} теперь требует
  // авторизации (раньше был открыт кому угодно с UUID обхода), поэтому
  // window.open(url) напрямую больше не сработает — заголовок Authorization
  // так не передать. Загружаем HTML через настроенный клиент и открываем
  // как blob-URL, печать/сохранение в PDF остаётся на браузере.
  openPdfReport: async (inspectionId: string) => {
    const res = await api.get(`/reports/pdf/${inspectionId}`, { responseType: 'text' })
    const blob = new Blob([res.data as string], { type: 'text/html' })
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
  },
}

// ── Issues ──
export const issuesApi = {
  create: (data: IssueCreate) =>
    api.post<IssueOut>('/issues/', data).then((r) => r.data),

  get: (id: string) => api.get<IssueOut>(`/issues/${id}`).then((r) => r.data),

  list: (params?: {
    site_id?: string; status?: string; criticality?: string;
    district_id?: string; assigned_to?: string; page?: number; page_size?: number
  }) =>
    api.get<IssueListOut>('/issues/', { params }).then((r) => r.data),

  update: (id: string, data: {
    status?: string; assigned_to?: string | null; due_date?: string; comment?: string; fix_comment?: string; reviewer_comment?: string
  }) =>
    api.put<IssueOut>(`/issues/${id}`, data).then((r) => r.data),

  uploadFixPhoto: (issueId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api
      .post<PhotoOut>(`/issues/${issueId}/fix-photos`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data)
  },

  uploadPhoto: (issueId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api
      .post<PhotoOut>(`/issues/${issueId}/photos`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data)
  },
}
