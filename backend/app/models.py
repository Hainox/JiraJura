"""SQLAlchemy ORM модели."""
import uuid
from datetime import datetime, timezone

from geoalchemy2 import Geometry
from sqlalchemy import (
    Column, ForeignKey, String, Integer, Numeric, Text, Boolean,
    Date, DateTime, Enum, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ── PostgreSQL ENUM типы (существующие в БД — создаём через create_type=False) ──

SITE_TYPE_ENUM = Enum(
    'Детская площадка', 'Спортивная площадка',
    name='site_type', create_type=False,
)

EQUIPMENT_TYPE_ENUM = Enum(
    'Качели', 'Горка', 'Турник', 'Песочница', 'Карусель',
    'Баскетбольное кольцо', 'Футбольные ворота', 'Тренажёр',
    'Скамейка', 'Урна', 'Ограждение', 'Покрытие', 'Прочее',
    name='equipment_type', create_type=False,
)

USER_ROLE_ENUM = Enum(
    'inspector', 'reviewer', 'admin',
    name='user_role', create_type=False,
)

INSPECTION_TYPE_ENUM = Enum(
    'regular', 'unscheduled', 'control', 'seasonal',
    name='inspection_type', create_type=False,
)

INSPECTION_STATUS_ENUM = Enum(
    'planned', 'in_progress', 'completed', 'issues_found', 'critical',
    name='inspection_status', create_type=False,
)

CHECKLIST_RESULT_ENUM = Enum(
    'ok', 'defect', 'not_applicable', 'not_checked',
    name='checklist_result', create_type=False,
)

PHOTO_TARGET_ENUM = Enum(
    'inspection', 'issue', 'equipment', 'checklist_answer', 'issue_fix',
    name='photo_target', create_type=False,
)

ISSUE_CRITICALITY_ENUM = Enum(
    'low', 'medium', 'high', 'critical',
    name='issue_criticality', create_type=False,
)

ISSUE_STATUS_ENUM = Enum(
    'open', 'assigned', 'in_work', 'fixed', 'control', 'closed', 'overdue', 'revision_needed',
    name='issue_status', create_type=False,
)

FEEDBACK_STATUS_ENUM = Enum(
    'new', 'in_review', 'resolved', 'dismissed',
    name='feedback_status', create_type=False,
)

FEEDBACK_REPORT_TYPE_ENUM = Enum(
    'site', 'app', 'other',
    name='feedback_report_type', create_type=False,
)


# ── Модели ──────────────────────────────────────────────────────

class District(Base):
    __tablename__ = "districts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False)
    code = Column(String(50))
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    courtyards = relationship("Courtyard", back_populates="district")
    users = relationship("User", back_populates="district_ref")


class Courtyard(Base):
    __tablename__ = "courtyards"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    district_id = Column(UUID(as_uuid=True), ForeignKey("districts.id"), nullable=False)
    name = Column(String(500), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        UniqueConstraint("district_id", "name"),
    )

    district = relationship("District", back_populates="courtyards")
    sites = relationship("Site", back_populates="courtyard")


class Site(Base):
    __tablename__ = "sites"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    courtyard_id = Column(UUID(as_uuid=True), ForeignKey("courtyards.id"), nullable=False)
    type = Column(SITE_TYPE_ENUM, nullable=False)
    area_m2 = Column(Numeric(10, 2), nullable=False)
    cleaning_type = Column(String(50), default="Ручная уборка")
    geometry = Column(Geometry("POLYGON", srid=4326), nullable=False)
    # GENERATED ALWAYS AS (ST_Centroid(geometry)) STORED в schema.sql —
    # Postgres поддерживает её сам при любом изменении geometry, приложение
    # никогда не должно писать в эту колонку.
    centroid = Column(Geometry("POINT", srid=4326))
    kml_original_id = Column(String(200))
    is_active = Column(Boolean, nullable=False, default=True)
    # Инспектор, за которым сейчас закреплена площадка — назначает
    # проверяющий/админ (см. routers/sites.py assign_site_inspector).
    # Не блокирует обход площадки другими инспекторами (маршруты в реальной
    # жизни пересекаются и меняются на ходу, см. комментарий про
    # ENABLE_DAILY_INSPECTION_LIMIT в inspections.py) — это только
    # ориентир "чья это площадка сегодня", не хард-ограничение.
    assigned_inspector_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), onupdate=_utcnow)

    courtyard = relationship("Courtyard", back_populates="sites")
    equipment = relationship("Equipment", back_populates="site")
    inspections = relationship("Inspection", back_populates="site")
    issues = relationship("Issue", back_populates="site_ref")
    assigned_inspector = relationship("User", foreign_keys=[assigned_inspector_id])


class Equipment(Base):
    __tablename__ = "equipment"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    type = Column(EQUIPMENT_TYPE_ENUM, nullable=False)
    name = Column(String(200))
    quantity = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    site = relationship("Site", back_populates="equipment")


class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    login = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(200), nullable=False)
    role = Column(USER_ROLE_ENUM, nullable=False)
    district_id = Column(UUID(as_uuid=True), ForeignKey("districts.id"), nullable=True)
    phone = Column(String(20))
    is_active = Column(Boolean, default=True)
    must_change_password = Column(Boolean, default=False)
    # Доп. пункт меню "Разработчик" в админ-панели (эксплуатационные
    # инструменты) — не отдельная роль, просто флаг на конкретном admin-
    # аккаунте, чтобы не захламлять меню остальным админам.
    is_developer = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    district_ref = relationship("District", back_populates="users")
    inspections = relationship(
        "Inspection", back_populates="inspector",
        primaryjoin="User.id == foreign(Inspection.inspector_id)",
    )
    assigned_issues = relationship(
        "Issue", back_populates="assigned_user",
        primaryjoin="User.id == foreign(Issue.assigned_to)",
    )


class UserInvite(Base):
    """Приглашение на регистрацию: админ создаёт со сгенерированной ролью/районом,
    сам пользователь по ссылке с токеном задаёт себе пароль."""
    __tablename__ = "user_invites"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    login = Column(String(50), unique=True, nullable=False)
    full_name = Column(String(200), nullable=False)
    role = Column(USER_ROLE_ENUM, nullable=False)
    district_id = Column(UUID(as_uuid=True), ForeignKey("districts.id"), nullable=True)
    token_hash = Column(String(128), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)


class ChecklistTemplate(Base):
    __tablename__ = "checklist_templates"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    site_type = Column(SITE_TYPE_ENUM)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    items = relationship("ChecklistItem", back_populates="template")


class IssueCategory(Base):
    __tablename__ = "issue_categories"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), unique=True, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    checklist_items = relationship("ChecklistItem", back_populates="category_ref")
    issues = relationship("Issue", back_populates="category_ref")


class ChecklistItem(Base):
    __tablename__ = "checklist_items"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("checklist_templates.id", ondelete="CASCADE"), nullable=False)
    category = Column(String(200))
    category_id = Column(UUID(as_uuid=True), ForeignKey("issue_categories.id"), nullable=False)
    question = Column(String(500), nullable=False)
    sort_order = Column(Integer, default=0)
    is_critical = Column(Boolean, default=False)
    requires_photo = Column(Boolean, default=False)
    # FALSE — админ "удалил" пункт через админ-панель. Не хард-delete: у
    # старых обходов уже есть checklist_answers, ссылающиеся на этот пункт
    # (FK без ondelete=CASCADE) — удаление сломало бы их историю.
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    template = relationship("ChecklistTemplate", back_populates="items")
    category_ref = relationship("IssueCategory", back_populates="checklist_items")


class Inspection(Base):
    __tablename__ = "inspections"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id"), nullable=False)
    inspector_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    template_id = Column(UUID(as_uuid=True), ForeignKey("checklist_templates.id"), nullable=True)
    type = Column(INSPECTION_TYPE_ENUM, nullable=False, default="regular")
    status = Column(INSPECTION_STATUS_ENUM, nullable=False, default="planned")
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    gps_lat = Column(Numeric(9, 6))
    gps_lon = Column(Numeric(9, 6))
    comment = Column(Text)
    reviewer_comment = Column(Text)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    site = relationship("Site", back_populates="inspections")
    inspector = relationship("User", back_populates="inspections", foreign_keys=[inspector_id])
    reviewed_by_user = relationship("User", foreign_keys=[reviewed_by])
    answers = relationship("ChecklistAnswer", back_populates="inspection")
    photos = relationship("Photo", back_populates="inspection",
                          primaryjoin="and_(Inspection.id==Photo.inspection_id, Photo.target_type=='inspection')",
                          viewonly=True)
    issues = relationship("Issue", back_populates="inspection_ref")


class ChecklistAnswer(Base):
    __tablename__ = "checklist_answers"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inspection_id = Column(UUID(as_uuid=True), ForeignKey("inspections.id", ondelete="CASCADE"), nullable=False)
    checklist_item_id = Column(UUID(as_uuid=True), ForeignKey("checklist_items.id"), nullable=False)
    result = Column(CHECKLIST_RESULT_ENUM, nullable=False)
    comment = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        UniqueConstraint("inspection_id", "checklist_item_id"),
    )

    inspection = relationship("Inspection", back_populates="answers")


class Photo(Base):
    __tablename__ = "photos"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_type = Column(PHOTO_TARGET_ENUM, nullable=False)
    inspection_id = Column(UUID(as_uuid=True), ForeignKey("inspections.id", ondelete="CASCADE"), nullable=True)
    issue_id = Column(UUID(as_uuid=True), ForeignKey("issues.id", ondelete="SET NULL"), nullable=True)
    equipment_id = Column(UUID(as_uuid=True), ForeignKey("equipment.id"), nullable=True)
    checklist_answer_id = Column(UUID(as_uuid=True), ForeignKey("checklist_answers.id", ondelete="SET NULL"), nullable=True)
    storage_path = Column(String(500), nullable=False)
    thumbnail_path = Column(String(500))
    gps_lat = Column(Numeric(9, 6))
    gps_lon = Column(Numeric(9, 6))
    taken_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    inspection = relationship("Inspection", back_populates="photos")


class Issue(Base):
    __tablename__ = "issues"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inspection_id = Column(UUID(as_uuid=True), ForeignKey("inspections.id"), nullable=False)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id"), nullable=False)
    # Пункт чек-листа, из-за которого замечание создано автоматически —
    # NULL для замечаний, заведённых вручную не по конкретному пункту.
    checklist_answer_id = Column(UUID(as_uuid=True), ForeignKey("checklist_answers.id", ondelete="SET NULL"), nullable=True)
    category_id = Column(UUID(as_uuid=True), ForeignKey("issue_categories.id"), nullable=False)
    title = Column(String(300), nullable=False)
    description = Column(Text)
    criticality = Column(ISSUE_CRITICALITY_ENUM, nullable=False, default="medium")
    status = Column(ISSUE_STATUS_ENUM, nullable=False, default="open")
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    due_date = Column(Date)
    fix_comment = Column(Text)
    reviewer_comment = Column(Text)
    executor_name = Column(String(300))
    fixed_at = Column(DateTime(timezone=True))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), onupdate=_utcnow)

    inspection_ref = relationship("Inspection", back_populates="issues")
    site_ref = relationship("Site", back_populates="issues")
    assigned_user = relationship("User", back_populates="assigned_issues", foreign_keys=[assigned_to])
    creator_ref = relationship("User", foreign_keys=[created_by])
    category_ref = relationship("IssueCategory", back_populates="issues")
    status_history = relationship("IssueStatusHistory", back_populates="issue")
    fix_photos = relationship("Photo",
                          primaryjoin="and_(Issue.id==Photo.issue_id, Photo.target_type=='issue_fix')",
                          viewonly=True)
    photos = relationship("Photo",
                          primaryjoin="and_(Issue.id==Photo.issue_id, Photo.target_type=='issue')",
                          viewonly=True)


class IssueStatusHistory(Base):
    __tablename__ = "issue_status_history"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    issue_id = Column(UUID(as_uuid=True), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    old_status = Column(ISSUE_STATUS_ENUM)
    new_status = Column(ISSUE_STATUS_ENUM, nullable=False)
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    comment = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    issue = relationship("Issue", back_populates="status_history")


class AuditLog(Base):
    """Журнал действий: кто, когда, что сделал."""
    __tablename__ = "audit_log"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(50), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(100), nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    user = relationship("User", foreign_keys=[user_id])


class FeedbackReport(Base):
    """Обращение с публичной веб-формы (/feedback) — без авторизации,
    заявитель может быть анонимным. Отдельная очередь для ручного разбора,
    не путать с Issue: сюда попадают жалобы граждан/сотрудников, а не
    находки инспектора при обходе.
    """
    __tablename__ = "feedback_reports"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_type = Column(FEEDBACK_REPORT_TYPE_ENUM, nullable=False, default="site")
    full_name = Column(String(200), nullable=True)
    phone = Column(String(20), nullable=True)
    location_text = Column(String(500), nullable=True)
    message = Column(Text, nullable=False)
    status = Column(FEEDBACK_STATUS_ENUM, nullable=False, default="new")
    admin_comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    attachments = relationship(
        "FeedbackAttachment", back_populates="report",
        cascade="all, delete-orphan", order_by="FeedbackAttachment.created_at",
    )


class FeedbackAttachment(Base):
    """Фото или файл (список и т.п.), приложенные к обращению — отдельная
    таблица, не Photo: та привязана к обходу/замечанию/оборудованию и
    подразумевает именно фотографию, а сюда можно прикладывать и xlsx/csv.
    """
    __tablename__ = "feedback_attachments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feedback_report_id = Column(UUID(as_uuid=True), ForeignKey("feedback_reports.id", ondelete="CASCADE"), nullable=False)
    storage_path = Column(String(500), nullable=False)
    original_filename = Column(String(255), nullable=True)
    content_type = Column(String(100), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    report = relationship("FeedbackReport", back_populates="attachments")
