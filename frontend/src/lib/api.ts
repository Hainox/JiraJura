import axios from 'axios'
import type {
  LoginRequest,
  LoginResponse,
  DistrictOut,
  SiteOut,
  SiteListOut,
  ChecklistTemplateOut,
  ChecklistItemOut,
  InspectionOut,
  InspectionListOut,
  ChecklistAnswerOut,
  IssueOut,
  IssueCreate,
  PhotoOut,
} from '@/types'

const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// Авто-прокидывание токена
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Обработка 401 — разлогин
api.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error.response?.status === 401) {
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
}

// ── Districts ──
export const districtsApi = {
  list: () => api.get<DistrictOut[]>('/districts/').then((r) => r.data),
}

// ── Sites ──
export const sitesApi = {
  list: (params?: { district_id?: string; site_type?: string }) =>
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

  list: (params?: { site_id?: string; status?: string }) =>
    api.get<InspectionListOut>('/inspections/', { params }).then((r) => r.data),

  update: (id: string, data: Record<string, unknown>) =>
    api.patch<InspectionOut>(`/inspections/${id}`, data).then((r) => r.data),

  complete: (id: string, data: { status: string; comment?: string; gps_lat?: number; gps_lon?: number }) =>
    api.patch<InspectionOut>(`/inspections/${id}`, data).then((r) => r.data),

  uploadPhoto: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api
      .post<PhotoOut>(`/inspections/${id}/photos`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data)
  },
}

// ── Issues ──
export const issuesApi = {
  create: (data: IssueCreate) =>
    api.post<IssueOut>('/issues/', data).then((r) => r.data),

  get: (id: string) => api.get<IssueOut>(`/issues/${id}`).then((r) => r.data),

  list: (params?: { inspection_id?: string }) =>
    api.get<IssueOut[]>('/issues/', { params }).then((r) => r.data),
}
