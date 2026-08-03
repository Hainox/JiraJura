"""Pydantic схемы для API."""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Аутентификация ─────────────────────────────────────────────

class LoginRequest(BaseModel):
    login: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    user: UserOut


class UserOut(BaseModel):
    id: UUID
    login: str
    full_name: str
    role: str
    district_id: Optional[UUID] = None
    phone: Optional[str] = None

    model_config = {"from_attributes": True}


class UserAdminOut(UserOut):
    """Расширенная карточка пользователя для админки (+ is_active)."""
    is_active: bool

    model_config = {"from_attributes": True}


class UserRoleUpdate(BaseModel):
    role: Optional[str] = None
    district_id: Optional[UUID] = None
    is_active: Optional[bool] = None


# ── Приглашения на регистрацию ────────────────────────────────

class UserInviteCreate(BaseModel):
    login: str = Field(min_length=3, max_length=50)
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


class UserInvitePreview(BaseModel):
    """То, что видит приглашённый на странице регистрации по токену."""
    full_name: str
    role: str


class InviteCompleteRequest(BaseModel):
    password: str = Field(min_length=8, max_length=200)


# ── Районы ─────────────────────────────────────────────────────

class DistrictOut(BaseModel):
    id: UUID
    name: str

    model_config = {"from_attributes": True}


# ── Дворы ──────────────────────────────────────────────────────

class CourtyardOut(BaseModel):
    id: UUID
    name: str
    district_id: UUID

    model_config = {"from_attributes": True}


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

    model_config = {"from_attributes": True}


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

    model_config = {"from_attributes": True}


class ChecklistTemplateOut(BaseModel):
    id: UUID
    name: str
    site_type: Optional[str]
    items: list[ChecklistItemOut]

    model_config = {"from_attributes": True}


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
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None
    answers: Optional[list[ChecklistAnswerIn]] = None


class PhotoOut(BaseModel):
    id: UUID
    target_type: str
    inspection_id: Optional[UUID]
    issue_id: Optional[UUID]
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


# ── Замечания ──────────────────────────────────────────────────

class IssueCreate(BaseModel):
    inspection_id: UUID
    title: str
    description: Optional[str] = None
    criticality: str = "medium"


class IssueUpdate(BaseModel):
    status: Optional[str] = None
    assigned_to: Optional[UUID] = None
    due_date: Optional[datetime] = None
    comment: Optional[str] = None  # для истории статуса


class IssueOut(BaseModel):
    id: UUID
    title: str
    description: Optional[str]
    criticality: str
    status: str
    site_id: UUID
    inspection_id: UUID
    assigned_to: Optional[UUID]
    due_date: Optional[datetime]
    created_at: datetime

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
