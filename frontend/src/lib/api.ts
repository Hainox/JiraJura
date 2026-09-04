import type {
  LoginRequest,
  LoginResponse,
  DistrictOut,
  DistrictAdminOut,
  CourtyardAdminOut,
  SiteOut,
  SiteListOut,
  ChecklistTemplateOut,
  ChecklistItemOut,
  InspectionOut,
  InspectionListOut,
  IssueOut,
  IssueCreate,
  IssueListOut,
  IssueCategoryOut,
  PhotoOut,
  UserOut,
  UserAdminOut,
  UserInviteCreate,
  UserInviteCreated,
  UserInvitePreview,
  UserInviteAdminOut,
  UserRoleUpdate,
  SelfUpdateRequest,
  PasswordResetOut,
  DashboardOut,
  SystemStatsOut,
  DiagnosticsLoginsOut,
  DiagnosticsMissingPhotosOut,
  DeployRequestOut,
  DeployStatusOut,
  FeedbackReportOut,
  FeedbackReportListOut,
  FeedbackAttachmentOut,
  StatsDashboardOut,
  StatsDynamicsOut,
  StatsCategoriesOut,
  StatsSectionsOut,
} from '@/types'

// Нативный fetch вместо axios: тот тянул в главный бандл ~46 kB ради
// возможностей (интерцепторы, оба адаптера XHR+fetch), которые тут не
// используются. Ниже — тонкая обёртка с ТЕМ ЖЕ контрактом ошибок, чтобы
// не трогать ни один из ~60 вызовов *.Api и обработку ошибок на страницах.
const BASE_URL = import.meta.env.VITE_API_URL || '/api/v1'
const DEFAULT_TIMEOUT_MS = 30000 // 30 секунд — без этого запрос может висеть бесконечно

// Фото грузят в поле на мобильном интернете — 30с общего таймаута часто не
// хватает (были жалобы на "Ошибка загрузки фото" именно в поле по LTE).
export const PHOTO_UPLOAD_TIMEOUT_MS = 90000

type ApiConfig = {
  params?: Record<string, string | number | boolean | null | undefined>
  headers?: Record<string, string>
  timeout?: number
  responseType?: 'json' | 'blob' | 'text'
}

// Контракт ошибки, совместимый с прежним axios:
//   - таймаут/сеть → error.code, без error.response;
//   - HTTP-ошибка  → error.response.status + error.response.data (JSON).
// Страницы читают err.response.data.detail и err.code === 'ECONNABORTED',
// поэтому форма сохраняется намеренно.
export class ApiError extends Error {
  response?: { status: number; data: unknown }
  code?: string

  constructor(message: string, init?: { code?: string; response?: { status: number; data: unknown } }) {
    super(message)
    this.name = 'ApiError'
    if (init?.code) this.code = init.code
    if (init?.response) this.response = init.response
  }
}

function buildQuery(params?: ApiConfig['params']): string {
  if (!params) return ''
  const qs = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    qs.append(key, String(value))
  }
  const s = qs.toString()
  return s ? `?${s}` : ''
}

async function parseBody(res: Response, responseType?: ApiConfig['responseType']): Promise<unknown> {
  if (responseType === 'blob') return res.blob()
  if (responseType === 'text') return res.text()
  const text = await res.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

function handleUnauthorized() {
  // На страницах логина и смены пароля 401 — ожидаемое поведение,
  // даём странице самой показать ошибку.
  const path = window.location.pathname
  if (path === '/login' || path === '/change-password') return
  localStorage.removeItem('access_token')
  localStorage.removeItem('user')
  window.location.href = '/login'
}

async function request<T>(
  method: string,
  url: string,
  body?: unknown,
  config: ApiConfig = {},
): Promise<{ data: T; status: number }> {
  const timeoutMs = config.timeout ?? DEFAULT_TIMEOUT_MS
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)

  const headers: Record<string, string> = { ...config.headers }
  const token = localStorage.getItem('access_token')
  if (token) headers.Authorization = `Bearer ${token}`

  let payload: BodyInit | undefined
  if (body !== undefined) {
    if (body instanceof FormData) {
      payload = body
      // multipart-boundary браузер проставит сам — руками его не задаём
      delete headers['Content-Type']
    } else {
      payload = JSON.stringify(body)
      headers['Content-Type'] = headers['Content-Type'] ?? 'application/json'
    }
  }

  try {
    const res = await fetch(BASE_URL + url + buildQuery(config.params), {
      method,
      headers,
      body: payload,
      signal: controller.signal,
    })
    const data = await parseBody(res, config.responseType)
    clearTimeout(timer)
    if (!res.ok) {
      if (res.status === 401) handleUnauthorized()
      throw new ApiError(`Request failed with status ${res.status}`, {
        response: { status: res.status, data },
      })
    }
    return { data: data as T, status: res.status }
  } catch (err) {
    clearTimeout(timer)
    if (err instanceof ApiError) throw err
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ApiError('Request timeout', { code: 'ECONNABORTED' })
    }
    throw new ApiError('Network error', { code: 'ERR_NETWORK' })
  }
}

export const api = {
  get: <T>(url: string, config?: ApiConfig) => request<T>('GET', url, undefined, config),
  post: <T>(url: string, data?: unknown, config?: ApiConfig) => request<T>('POST', url, data, config),
  patch: <T>(url: string, data?: unknown, config?: ApiConfig) => request<T>('PATCH', url, data, config),
  put: <T>(url: string, data?: unknown, config?: ApiConfig) => request<T>('PUT', url, data, config),
  delete: <T>(url: string, config?: ApiConfig) => request<T>('DELETE', url, undefined, config),
}

// Человекочитаемая причина неудачи загрузки — вместо одного безликого
// тоста на все случаи (таймаут/сеть/413/500 звучали одинаково и не
// давали понять, что чинить: ждать сигнал получше или искать баг на сервере).
export function describeUploadError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'ECONNABORTED') return 'Превышено время ожидания — проверьте связь и попробуйте ещё раз'
    if (!error.response) return 'Нет соединения с сервером — проверьте интернет'
    if (error.response.status === 413) return 'Файл слишком большой для сервера'
    if (error.response.status === 401) return 'Сессия истекла — перезайдите в приложение'
  }
  return 'Ошибка загрузки фото'
}

export function describeRegistrationError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'ECONNABORTED') return 'Сервер отвечает слишком долго — проверьте связь и попробуйте ещё раз'
    if (!error.response) return 'Нет соединения с сервером — проверьте интернет'
    const data = error.response.data as { detail?: unknown } | null
    const detail = typeof data?.detail === 'string' ? data.detail : ''
    if (error.response.status === 409) return detail || 'Этот логин уже зарегистрирован. Обратитесь к администратору за новой ссылкой.'
    if (error.response.status === 404 || error.response.status === 410) return 'Ссылка недействительна или уже использована. Попросите администратора выдать новую.'
    if (error.response.status >= 500) return 'Сервер не смог завершить регистрацию. Попробуйте ещё раз через минуту.'
    if (detail) return detail
  }
  return 'Не удалось завершить регистрацию. Попробуйте ещё раз или обратитесь к администратору.'
}

// Как и describeRegistrationError — после отсева на сервере
// (validate_password_strength: длина, буквы+цифры для короче 12 символов,
// словарь тривиальных заготовок вроде «12345678») пользователь должен видеть
// именно эту причину, а не общий «не удалось сменить пароль».
export function describePasswordError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'ECONNABORTED') return 'Сервер отвечает слишком долго — проверьте связь и попробуйте ещё раз'
    if (!error.response) return 'Нет соединения с сервером — проверьте интернет'
    const data = error.response.data as { detail?: unknown } | null
    const detail = typeof data?.detail === 'string' ? data.detail : ''
    if (detail) return detail
  }
  return 'Не удалось сменить пароль. Попробуйте ещё раз.'
}

// Пользователь сообщил, что «обход не завершается» — расследование показало,
// что PATCH /inspections/{id} действительно может вернуть конкретную причину
// (нужно фото для requires_photo-пункта, обход уже проверен и недоступен для
// правки и т.п.), но save/complete/review/return в InspectionPage глотали её
// в один и тот же безликий «Ошибка завершения»/«Ошибка сохранения» —
// ни пользователю, ни при разборе жалобы постфактум не было видно, что
// именно отклонил сервер. Тот же приём, что уже используется в
// describeRegistrationError/describePasswordError.
export function describeInspectionUpdateError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'ECONNABORTED') return 'Превышено время ожидания — проверьте связь и попробуйте ещё раз'
    if (!error.response) return 'Нет соединения с сервером — проверьте интернет'
    const data = error.response.data as { detail?: unknown } | null
    const detail = typeof data?.detail === 'string' ? data.detail : ''
    if (detail) return detail
  }
  return 'Не удалось сохранить обход. Попробуйте ещё раз.'
}

// ── Auth ──
export const authApi = {
  login: (data: LoginRequest) =>
    api.post<LoginResponse>('/auth/login', data).then((r) => r.data),

  me: () => api.get<UserOut>('/auth/me').then((r) => r.data),

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

  // Полный список приглашений (включая использованные/истёкшие) — для
  // раздела «Приглашения» в «Пользователях». listUsers/createInvite не
  // трогают, тем по-прежнему нужны только активные.
  listInvites: () => api.get<UserInviteAdminOut[]>('/auth/invites').then((r) => r.data),

  reissueInvite: (id: string) =>
    api.post<UserInviteCreated>(`/auth/invites/${id}/reissue`).then((r) => r.data),

  revokeInvite: (id: string) =>
    api.delete(`/auth/invites/${id}`).then((r) => r.data),
}

// ── Districts ──
export const districtsApi = {
  list: () => api.get<DistrictOut[]>('/districts/').then((r) => r.data),

  listAdmin: () => api.get<DistrictAdminOut[]>('/districts/admin').then((r) => r.data),

  rename: (id: string, name: string) =>
    api.patch<DistrictOut>(`/districts/${id}`, { name }).then((r) => r.data),

  // Переносит все дворы/площадки из id в intoDistrictId и удаляет
  // опустевший id — инструмент починки задвоенных районов вида
  // "Бескудниковский;Восточное Дегунино" через UI, не через psql.
  merge: (id: string, intoDistrictId: string) =>
    api.post<DistrictOut>(`/districts/${id}/merge`, { into_district_id: intoDistrictId }).then((r) => r.data),
}

// ── Дворы (админ) ──
export const courtyardsApi = {
  list: (params?: { district_id?: string; search?: string }) =>
    api.get<CourtyardAdminOut[]>('/courtyards/', { params }).then((r) => r.data),

  update: (id: string, data: { name?: string; district_id?: string; section?: string | null }) =>
    api.patch<CourtyardAdminOut>(`/courtyards/${id}`, data).then((r) => r.data),
}

// ── Sites ──
export const sitesApi = {
  // параметр фильтра по типу в API называется `type` и принимает значение
  // enum'а site_type как есть: «Детская площадка» / «Спортивная площадка»
  list: (params?: {
    district_id?: string; courtyard_id?: string; type?: string; page_size?: number
    assigned_to_me?: boolean; include_inactive?: boolean
  }) =>
    api.get<SiteListOut>('/sites/', { params }).then((r) => r.data),

  get: (id: string) => api.get<SiteOut>(`/sites/${id}`).then((r) => r.data),

  update: (id: string, data: { type?: string; area_m2?: number; cleaning_type?: string; is_active?: boolean; courtyard_id?: string }) =>
    api.patch<SiteOut>(`/sites/${id}`, data).then((r) => r.data),

  // inspector_id: null снимает назначение — явно, не "не менять" (см.
  // комментарий у SiteAssignUpdate в backend/app/schemas.py)
  assign: (siteId: string, inspectorId: string | null) =>
    api.patch<SiteOut>(`/sites/${siteId}/assign`, { inspector_id: inspectorId }).then((r) => r.data),
}

// ── Checklists ──
export const checklistsApi = {
  template: (params?: { site_type?: string }) =>
    api.get<ChecklistTemplateOut[]>('/sites/templates/checklist', { params }).then((r) => r.data),

  // Как template(), но включает отключённые (is_active=false) пункты —
  // только для админ-панели, чтобы их можно было снова включить.
  listAdminTemplates: () =>
    api.get<ChecklistTemplateOut[]>('/checklists/templates').then((r) => r.data),

  createItem: (data: { template_id: string; category?: string; question: string; sort_order?: number; is_critical?: boolean; requires_photo?: boolean }) =>
    api.post<ChecklistItemOut>('/checklists/items', data).then((r) => r.data),

  updateItem: (id: string, data: { category?: string; question?: string; sort_order?: number; is_critical?: boolean; requires_photo?: boolean; is_active?: boolean }) =>
    api.patch<ChecklistItemOut>(`/checklists/items/${id}`, data).then((r) => r.data),

  deleteItem: (id: string) =>
    api.delete<ChecklistItemOut>(`/checklists/items/${id}`).then((r) => r.data),
}

// ── Inspections ──
export const inspectionsApi = {
  create: (siteId: string) =>
    api.post<InspectionOut>('/inspections/', { site_id: siteId }).then((r) => r.data),

  get: (id: string) => api.get<InspectionOut>(`/inspections/${id}`).then((r) => r.data),

  list: (params?: { site_id?: string; status?: string; exclude_status?: string; district_id?: string; page?: number; page_size?: number; all_in_district?: boolean }) =>
    api.get<InspectionListOut>('/inspections/', { params }).then((r) => r.data),

  update: (id: string, data: Record<string, unknown>) =>
    api.patch<InspectionOut>(`/inspections/${id}`, data).then((r) => r.data),

  bulkAccept: (ids: string[]) =>
    api.post<{ accepted: number; skipped: number }>('/inspections/bulk-accept', { ids }).then((r) => r.data),

  uploadPhoto: (id: string, file: File, checklistAnswerId?: string) => {
    const form = new FormData()
    form.append('file', file)
    const params = checklistAnswerId ? `?checklist_answer_id=${checklistAnswerId}` : ''
    return api
      .post<PhotoOut>(`/inspections/${id}/photos${params}`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: PHOTO_UPLOAD_TIMEOUT_MS,
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
  exportXlsx: async (params?: { district_id?: string; date_from?: string; date_to?: string; all_time?: boolean }) => {
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

// ── Statistics v2 ──
type StatsParams = { district_id?: string; date_from?: string; date_to?: string; all_time?: boolean }

export const statsApi = {
  dashboard: (params?: StatsParams) =>
    api.get<StatsDashboardOut>('/stats/dashboard', { params }).then((r) => r.data),
  dynamics: (params?: StatsParams) =>
    api.get<StatsDynamicsOut>('/stats/dynamics', { params }).then((r) => r.data),
  categories: (params?: StatsParams) =>
    api.get<StatsCategoriesOut>('/stats/categories', { params }).then((r) => r.data),
  // Свод по участкам — только внутри одного района (district_id обязателен
  // на бэкенде), для окружного штаба не используется.
  sections: (params: StatsParams & { district_id: string }) =>
    api.get<StatsSectionsOut>('/stats/sections', { params }).then((r) => r.data),
  downloadShtab: async (params?: StatsParams) => {
    const res = await api.get('/stats/shtab.pptx', { params, responseType: 'blob' })
    const url = URL.createObjectURL(res.data as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `shtab_${params?.date_from || 'period'}_${params?.date_to || 'period'}.pptx`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },
}

// ── Issues ──
export const issuesApi = {
  create: (data: IssueCreate) =>
    api.post<IssueOut>('/issues/', data).then((r) => r.data),

  categories: () =>
    api.get<IssueCategoryOut[]>('/issues/categories').then((r) => r.data),

  get: (id: string) => api.get<IssueOut>(`/issues/${id}`).then((r) => r.data),

  list: (params?: {
    site_id?: string; inspection_id?: string; status?: string; criticality?: string;
    district_id?: string; assigned_to?: string; page?: number; page_size?: number
  }) =>
    api.get<IssueListOut>('/issues/', { params }).then((r) => r.data),

  update: (id: string, data: {
    status?: string; assigned_to?: string | null; due_date?: string | null; comment?: string; fix_comment?: string; reviewer_comment?: string
    executor_name?: string | null; category_id?: string | null
  }) =>
    api.put<IssueOut>(`/issues/${id}`, data).then((r) => r.data),

  uploadFixPhoto: (issueId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api
      .post<PhotoOut>(`/issues/${issueId}/fix-photos`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: PHOTO_UPLOAD_TIMEOUT_MS,
      })
      .then((r) => r.data)
  },

  uploadPhoto: (issueId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api
      .post<PhotoOut>(`/issues/${issueId}/photos`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: PHOTO_UPLOAD_TIMEOUT_MS,
      })
      .then((r) => r.data)
  },
}

// ── Разработчик (эксплуатационная сводка, диагностика, деплой) ──
export const systemApi = {
  stats: () => api.get<SystemStatsOut>('/system/stats').then((r) => r.data),

  diagnosticsLogins: () =>
    api.get<DiagnosticsLoginsOut>('/system/diagnostics/logins').then((r) => r.data),

  diagnosticsMissingPhotos: (address: string, district?: string) =>
    api
      .get<DiagnosticsMissingPhotosOut>('/system/diagnostics/missing-photos', { params: { address, district } })
      .then((r) => r.data),

  requestDeploy: (note?: string) =>
    api.post<DeployRequestOut>('/system/deploy/request', { note }).then((r) => r.data),

  deployStatus: () => api.get<DeployStatusOut>('/system/deploy/status').then((r) => r.data),
}

// ── Обращения ──
export const feedbackApi = {
  // Публичный — без авторизации, вызывается с /feedback до логина
  submit: (data: { report_type?: string; full_name?: string; phone?: string; location_text?: string; message: string }) =>
    api.post<FeedbackReportOut>('/feedback/', data).then((r) => r.data),

  list: (params?: { status?: string; report_type?: string }) =>
    api.get<FeedbackReportListOut>('/feedback/', { params }).then((r) => r.data),

  update: (id: string, data: { status?: string; admin_comment?: string }) =>
    api.patch<FeedbackReportOut>(`/feedback/${id}`, data).then((r) => r.data),

  // Публичный — без авторизации, вызывается сразу после submit() с /feedback
  uploadAttachment: (reportId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api
      .post<FeedbackAttachmentOut>(`/feedback/${reportId}/attachments`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: PHOTO_UPLOAD_TIMEOUT_MS,
      })
      .then((r) => r.data)
  },

  // Тот же принцип, что и reportsApi.exportXlsx — blob через настроенный
  // клиент (нужен Authorization-заголовок, обычная ссылка не подходит).
  exportXlsx: async (params?: { status?: string; report_type?: string }) => {
    const res = await api.get('/feedback/export.xlsx', { params, responseType: 'blob' })
    const url = URL.createObjectURL(res.data as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `обращения_${new Date().toISOString().slice(0, 10)}.xlsx`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },
}
