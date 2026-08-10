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
}

export interface SiteListOut {
  total: number
  items: SiteOut[]
}

// ── Checklist ──
export interface ChecklistItemOut {
  id: string // UUID
  category?: string
  question: string // не description!
  sort_order: number
  is_critical: boolean
  requires_photo: boolean
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
  inspections_total: number
  inspections_completed: number
  inspections_in_progress: number
  issues_total: number
  issues_open: number
  issues_fixed: number
  issues_revision_needed: number
  issues_closed: number
}

export interface DashboardOut {
  districts: DashboardDistrictRow[]
  totals: DashboardDistrictRow
}
