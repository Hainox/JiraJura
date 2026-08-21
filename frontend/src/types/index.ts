// Типы данных для приложения «Журнал обхода площадок САО» — соответствуют backend schemas.py

// ── Auth ──
export interface LoginRequest {
  login: string // backend: login, не username
  password: string
}

export interface UserOut {
  id: string // UUID
  login: string
  full_name: string
  role: string
  district_id?: string
  phone?: string
  is_developer?: boolean
}

export interface LoginResponse {
  access_token: string
  user: UserOut
  must_change_password?: boolean
}

export type Role = 'inspector' | 'reviewer' | 'admin'

// ── Пользователи / приглашения (админка) ──
export interface UserAdminOut extends UserOut {
  is_active: boolean
}

export interface UserInviteCreate {
  login: string
  full_name: string
  role: Role
  district_id?: string
}

export interface UserInviteCreated {
  id: string
  login: string
  full_name: string
  role: Role
  token: string
  expires_at: string
}

export interface UserInvitePreview {
  full_name: string
  role: Role
}

export interface UserRoleUpdate {
  role?: Role
  district_id?: string | null
  is_active?: boolean
  full_name?: string
  phone?: string | null
  is_developer?: boolean
}

export interface SelfUpdateRequest {
  full_name?: string
  phone?: string
}

export interface PasswordResetOut {
  new_password: string
}

// ── Courier / Courtyard ──
export interface CourtyardOut {
  id: string
  name: string
  district_id: string
}

// ── Districts ──
export interface DistrictOut {
  id: string
  name: string
}

export interface DistrictAdminOut extends DistrictOut {
  courtyards_count: number
  sites_count: number
}

export interface CourtyardAdminOut {
  id: string
  name: string
  district_id: string
  district_name: string
  sites_count: number
}

// ── Sites ──
export interface SiteOut {
  id: string
  type: string
  area_m2: number | string
  courtyard: CourtyardOut
  district: DistrictOut
  is_active: boolean
  lat?: number | null
  lon?: number | null
  assigned_inspector?: UserOut | null
}

export interface SiteListOut {
  total: number
  items: SiteOut[]
}

// ── Checklist ──
export interface ChecklistItemOut {
  id: string // UUID
  category?: string
  category_id?: string
  category_name?: string
  question: string // не description!
  sort_order: number
  is_critical: boolean
  requires_photo: boolean
  is_active: boolean
}

export interface ChecklistTemplateOut {
  id: string
  name: string
  site_type?: string
  items: ChecklistItemOut[]
}

// ── Inspections ──
export interface ChecklistAnswerIn {
  checklist_item_id: string
  result: string // не is_ok boolean!
  comment?: string
}

export interface ChecklistAnswerOut {
  id: string
  checklist_item_id: string
  result: string
  comment?: string
}

export interface InspectionCreate {
  site_id: string
  type?: string
}

export interface PhotoOut {
  id: string
  target_type: string
  inspection_id?: string
  issue_id?: string
  checklist_answer_id?: string
  url: string
  thumbnail_url?: string
  gps_lat?: number | string
  gps_lon?: number | string
  taken_at?: string
  created_at: string
}

export interface InspectionOut {
  id: string
  site_id: string
  inspector: UserOut
  type: string
  status: string
  started_at?: string
  completed_at?: string
  gps_lat?: number | string
  gps_lon?: number | string
  comment?: string
  reviewer_comment?: string
  reviewed_by?: UserOut | null
  reviewed_at?: string
  created_at: string
  site: SiteOut
  answers: ChecklistAnswerOut[]
  issues_count: number
  is_green: boolean
  photos_count: number
  photos?: PhotoOut[]
}

export interface InspectionListOut {
  total: number
  items: InspectionOut[]
}

// ── Issues ──
export interface IssueCreate {
  inspection_id: string
  title: string // обязательное поле!
  description?: string
  criticality?: string // по умолчанию medium
  category_id?: string
}

export interface IssueCategoryOut {
  id: string
  name: string
  sort_order: number
}

export interface IssueOut {
  id: string
  title: string
  description?: string
  criticality: string
  status: string
  site_id: string
  inspection_id: string
  assigned_to?: string
  assigned_user?: UserOut | null
  due_date?: string
  created_by: string
  creator?: UserOut | null
  site_name?: string
  district_name?: string
  fix_comment?: string
  reviewer_comment?: string
  executor_name?: string
  category_id?: string
  category_name?: string
  is_overdue: boolean
  photos?: PhotoOut[]
  fix_photos?: PhotoOut[]
  created_at: string
  updated_at?: string
}

export interface IssueListOut {
  total: number
  items: IssueOut[]
}

// ── Reports ──
export interface ReportOut {
  district_id: string
  district_name: string
  total_sites: number
  inspected_sites: number
  issues_open?: number
  issues_overdue?: number
  issues_created?: number
  issues_closed?: number
}

// ── Dashboard ──
export interface DashboardDistrictRow {
  district_id: string
  district_name: string
  total_sites: number
  // Охват: сколько РАЗНЫХ площадок доведено до финального статуса за период.
  // «Зелёные» обходы идут в «проверено», даже если дефектов ноль.
  sites_inspected: number
  sites_not_inspected: number
  inspections_total: number
  inspections_completed: number
  inspections_in_progress: number
  // Результат завершённых обходов: без нарушений vs с нарушениями.
  inspections_ok: number
  inspections_with_defects: number
  // Реально выявлено при обходе (чек-лист, result='defect') — не зависит от
  // того, оформлено ли отдельное замечание. См. issues_total ниже.
  checklist_defects: number
  issues_total: number
  issues_open: number
  issues_fixed: number
  issues_revision_needed: number
  issues_closed: number
  issues_overdue: number
}

export interface DashboardOut {
  districts: DashboardDistrictRow[]
  totals: DashboardDistrictRow
}

export interface StatsPeriod { date_from: string; date_to: string }

export interface StatsDistrictRow {
  district_id: string
  district_name: string
  total_sites: number
  sites_inspected: number
  coverage_pct: number
  inspections_total: number
  inspections_green: number
  inspections_with_defects: number
  issues_found: number
  issues_closed: number
  issues_on_check: number
  issues_revision: number
  issues_in_work: number
  issues_open: number
  issues_not_fixed: number
  issues_overdue: number
  issues_closed_pct: number
}

export interface StatsDashboardOut {
  period: StatsPeriod
  timezone: string
  generated_at: string
  methodology: 'v2'
  districts: StatsDistrictRow[]
  totals: StatsDistrictRow
}

export interface StatsDynamicsDay {
  date: string
  inspections: number
  issues_found: number
  closure_events: number
}

export interface StatsDynamicsOut {
  period: StatsPeriod
  timezone: string
  generated_at: string
  methodology: 'v2'
  days: StatsDynamicsDay[]
}

export interface StatsCategoryRow {
  category_id: string
  name: string
  sort_order: number
  found: number
  closed: number
  on_check: number
  revision: number
  in_work: number
  open: number
  not_fixed: number
  overdue: number
  closed_pct: number
}

export interface StatsCategoriesOut {
  period: StatsPeriod
  timezone: string
  generated_at: string
  methodology: 'v2'
  categories: StatsCategoryRow[]
}

// ── Эксплуатационная сводка ("Разработчик") ──
export interface SystemStatsOut {
  app_env: string
  db_ok: boolean
  uptime_seconds: number
  counts: Record<string, number>
  uploads_size_mb: number
}

// ── Обращения (публичная веб-форма) ──
export type FeedbackStatus = 'new' | 'in_review' | 'resolved' | 'dismissed'
export type FeedbackReportType = 'site' | 'app' | 'other'

export interface FeedbackAttachmentOut {
  id: string
  url: string
  original_filename: string | null
  content_type: string | null
  size_bytes: number | null
  created_at: string
}

export interface FeedbackReportOut {
  id: string
  report_type: FeedbackReportType
  full_name: string | null
  phone: string | null
  location_text: string | null
  message: string
  status: FeedbackStatus
  admin_comment: string | null
  attachments: FeedbackAttachmentOut[]
  created_at: string
  resolved_at: string | null
}

export interface FeedbackReportListOut {
  total: number
  items: FeedbackReportOut[]
}
