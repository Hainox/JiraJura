"""Pydantic схемы для API."""
from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints


# ── Аутентификация ─────────────────────────────────────────────

# Логин: обрезаем случайные пробелы по краям (копипаст), 3..50 символов.
# Сознательно НЕ ограничиваем алфавит: в истории есть логины-кириллица и
# логины-транслитерации, жёсткий regex залочил бы уже существующие аккаунты.
Login = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=50)]


class LoginRequest(BaseModel):
    login: Login
    # max_length — только против гигантского тела запроса; проверку пароля
    # делаем как и раньше (bcrypt учитывает первые 72 байта).
    password: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    user: UserOut
    must_change_password: bool = False


class UserOut(BaseModel):
    id: UUID
    login: str
    full_name: str
    role: str
    district_id: Optional[UUID] = None
    phone: Optional[str] = None
    is_developer: bool = False

    model_config = {"from_attributes": True}


class UserAdminOut(UserOut):
    """Расширенная карточка пользователя для админки (+ is_active)."""
    is_active: bool

    model_config = {"from_attributes": True}


class UserRoleUpdate(BaseModel):
    role: Optional[str] = None
    district_id: Optional[UUID] = None
    is_active: Optional[bool] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    is_developer: Optional[bool] = None


class SelfUpdateRequest(BaseModel):
    """Самостоятельное редактирование профиля — только своих ФИО/телефона,
    без role/district_id/is_active (те меняет только admin)."""
    full_name: Optional[str] = None
    phone: Optional[str] = None


class PasswordResetOut(BaseModel):
    new_password: str


class ChangePasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=72)
    # Не нужен при принудительной смене после сброса админом — пользователь
    # только что подтвердил временный пароль самим входом. Обязателен при
    # обычной самостоятельной смене (см. change_password) — иначе кто угодно
    # с уже открытой чужой сессией (общее устройство в поле) мог бы тихо
    # перехватить аккаунт, просто задав новый пароль без знания старого.
    current_password: Optional[str] = None


# ── Приглашения на регистрацию ────────────────────────────────

class UserInviteCreate(BaseModel):
    login: Login
    full_name: str = Field(min_length=1, max_length=200)
    role: str
    district_id: Optional[UUID] = None


class UserInviteCreated(BaseModel):
    """Ответ на создание инвайта — токен возвращается только один раз."""
    id: UUID
    login: str
    full_name: str
    role: str
    token: str
    expires_at: datetime


class UserInvitePending(BaseModel):
    """Ещё не завершённое приглашение — для списка в админке и для
    bulk_invite.py (проверка "этому человеку уже отправляли" перед
    созданием нового приглашения под другим логином)."""
    id: UUID
    login: str
    full_name: str
    role: str
    district_id: Optional[UUID] = None
    created_at: datetime
    expires_at: datetime

    model_config = {"from_attributes": True}


class UserInvitePreview(BaseModel):
    """То, что видит приглашённый на странице регистрации по токену."""
    full_name: str
    role: str


class InviteCompleteRequest(BaseModel):
    password: str = Field(min_length=8, max_length=72)


# ── Районы ─────────────────────────────────────────────────────

class DistrictOut(BaseModel):
    id: UUID
    name: str

    model_config = {"from_attributes": True}


class DistrictAdminOut(BaseModel):
    id: UUID
    name: str
    courtyards_count: int
    sites_count: int


class DistrictUpdate(BaseModel):
    name: str


class DistrictMergeRequest(BaseModel):
    # Переносит все дворы из текущего района в этот и удаляет текущий
    # (становится пустым) — способ убрать задвоенные/битые районы вроде
    # "Бескудниковский;Восточное Дегунино" через UI, не руками в БД.
    into_district_id: UUID


# ── Дворы ──────────────────────────────────────────────────────

class CourtyardOut(BaseModel):
    id: UUID
    name: str
    district_id: UUID

    model_config = {"from_attributes": True}


class CourtyardAdminOut(CourtyardOut):
    district_name: str
    sites_count: int


class CourtyardUpdate(BaseModel):
    name: Optional[str] = None
    district_id: Optional[UUID] = None


# ── Площадки ───────────────────────────────────────────────────

class SiteOut(BaseModel):
    id: UUID
    type: str
    area_m2: Decimal
    courtyard: CourtyardOut
    district: DistrictOut
    is_active: bool
    lat: Optional[float] = None
    lon: Optional[float] = None
    assigned_inspector: Optional[UserOut] = None

    model_config = {"from_attributes": True}


class SiteAssignUpdate(BaseModel):
    # null снимает назначение — не Optional-как-"не менять", а реальное
    # целевое состояние, поэтому в роутере проверяется наличие поля, а
    # не его значение (та же логика, что для issues due_date/assigned_to).
    inspector_id: Optional[UUID] = None


class SiteAdminUpdate(BaseModel):
    type: Optional[str] = None
    area_m2: Optional[Decimal] = None
    cleaning_type: Optional[str] = None
    is_active: Optional[bool] = None
    courtyard_id: Optional[UUID] = None


class SiteListOut(BaseModel):
    total: int
    items: list[SiteOut]


# ── Чек-листы ──────────────────────────────────────────────────

class ChecklistItemOut(BaseModel):
    id: UUID
    category: Optional[str]
    question: str
    sort_order: int
    is_critical: bool
    requires_photo: bool
    is_active: bool = True

    model_config = {"from_attributes": True}


class ChecklistTemplateOut(BaseModel):
    id: UUID
    name: str
    site_type: Optional[str]
    items: list[ChecklistItemOut]

    model_config = {"from_attributes": True}


class ChecklistItemCreate(BaseModel):
    template_id: UUID
    category: Optional[str] = None
    question: str
    sort_order: int = 0
    is_critical: bool = False
    requires_photo: bool = False


class ChecklistItemUpdate(BaseModel):
    category: Optional[str] = None
    question: Optional[str] = None
    sort_order: Optional[int] = None
    is_critical: Optional[bool] = None
    requires_photo: Optional[bool] = None
    is_active: Optional[bool] = None


# ── Обходы ─────────────────────────────────────────────────────

class InspectionCreate(BaseModel):
    site_id: UUID
    type: str = "regular"


class ChecklistAnswerIn(BaseModel):
    checklist_item_id: UUID
    result: str
    comment: Optional[str] = None


class InspectionUpdate(BaseModel):
    status: Optional[str] = None
    comment: Optional[str] = None
    reviewer_comment: Optional[str] = None
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None
    answers: Optional[list[ChecklistAnswerIn]] = None


class PhotoOut(BaseModel):
    id: UUID
    target_type: str
    inspection_id: Optional[UUID]
    issue_id: Optional[UUID]
    checklist_answer_id: Optional[UUID] = None
    url: str
    thumbnail_url: Optional[str]
    gps_lat: Optional[Decimal]
    gps_lon: Optional[Decimal]
    taken_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class InspectionOut(BaseModel):
    id: UUID
    site_id: UUID
    inspector: UserOut
    type: str
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    gps_lat: Optional[Decimal]
    gps_lon: Optional[Decimal]
    comment: Optional[str]
    reviewer_comment: Optional[str] = None
    reviewed_by: Optional[UserOut] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    site: SiteOut
    answers: list[ChecklistAnswerOut] = []
    issues_count: int = 0
    photos_count: int = 0
    photos: list[PhotoOut] = []

    model_config = {"from_attributes": True}


class ChecklistAnswerOut(BaseModel):
    id: UUID
    checklist_item_id: UUID
    result: str
    comment: Optional[str]

    model_config = {"from_attributes": True}


class InspectionListOut(BaseModel):
    total: int
    items: list[InspectionOut]


class InspectionBulkAcceptRequest(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=500)


class InspectionBulkAcceptOut(BaseModel):
    accepted: int
    skipped: int


# ── Замечания ──────────────────────────────────────────────────

class IssueCreate(BaseModel):
    inspection_id: UUID
    title: str
    description: Optional[str] = None
    criticality: str = "medium"


class IssueUpdate(BaseModel):
    status: Optional[str] = None
    assigned_to: Optional[UUID] = None
    due_date: Optional[date] = None
    comment: Optional[str] = None  # для истории статуса
    fix_comment: Optional[str] = None  # описание исправления
    reviewer_comment: Optional[str] = None  # комментарий проверяющего (при приёмке/возврате)


class IssueOut(BaseModel):
    id: UUID
    title: str
    description: Optional[str]
    criticality: str
    status: str
    site_id: UUID
    inspection_id: UUID
    assigned_to: Optional[UUID] = None
    assigned_user: Optional[UserOut] = None
    due_date: Optional[date] = None
    created_by: UUID
    creator: Optional[UserOut] = None
    site_name: Optional[str] = None
    district_name: Optional[str] = None
    fix_comment: Optional[str] = None
    reviewer_comment: Optional[str] = None
    photos: list[PhotoOut] = []
    fix_photos: list[PhotoOut] = []
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class IssueListOut(BaseModel):
    total: int
    items: list[IssueOut]


# ── Отчёты ─────────────────────────────────────────────────────

class ReportWeeklyOut(BaseModel):
    district_id: UUID
    district_name: str
    total_sites: int
    inspected_sites: int
    issues_open: int
    issues_overdue: int


class ReportMonthlyOut(BaseModel):
    district_id: UUID
    district_name: str
    total_sites: int
    inspected_sites: int
    issues_created: int
    issues_closed: int
    issues_overdue: int


# ── Дашборд админа ─────────────────────────────────────────────

class DashboardDistrictRow(BaseModel):
    district_id: UUID
    district_name: str
    total_sites: int
    inspections_total: int
    inspections_completed: int
    inspections_in_progress: int
    # Реально выявлено при обходе (чек-лист, result='defect') — не зависит от
    # того, оформил ли инспектор отдельное замечание. См. issues_total ниже:
    # оформление замечания — необязательный второй шаг, и по нему одному
    # нельзя судить о том, сколько проблем реально нашли в районе.
    checklist_defects: int
    issues_total: int
    issues_open: int
    issues_fixed: int
    issues_revision_needed: int
    issues_closed: int


class DashboardOut(BaseModel):
    districts: list[DashboardDistrictRow]
    totals: DashboardDistrictRow


# ── Обращения (публичная веб-форма) ──────────────────────────────

class FeedbackReportCreate(BaseModel):
    # Явная валидация вместо тихого приведения невалидного значения к "site"
    # в роутере: опечатка в типе раньше молча загрязняла бакет "Площадка".
    report_type: Literal["site", "app", "other"] = "site"
    full_name: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=20)
    location_text: Optional[str] = Field(None, max_length=500)
    message: str = Field(..., min_length=5, max_length=3000)


class FeedbackReportUpdate(BaseModel):
    status: Optional[str] = None
    admin_comment: Optional[str] = None


class FeedbackAttachmentOut(BaseModel):
    id: UUID
    url: str
    original_filename: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackReportOut(BaseModel):
    id: UUID
    report_type: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    location_text: Optional[str] = None
    message: str
    status: str
    admin_comment: Optional[str] = None
    attachments: list[FeedbackAttachmentOut] = []
    created_at: datetime
    resolved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class FeedbackReportListOut(BaseModel):
    total: int
    items: list[FeedbackReportOut]
