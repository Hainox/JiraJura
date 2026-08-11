-- ============================================================
-- Электронный журнал обхода площадок САО г. Москвы
-- DDL: PostgreSQL 15+ / PostGIS 3+
-- ============================================================

-- Расширения
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- 1. ТЕРРИТОРИАЛЬНАЯ ИЕРАРХИЯ
-- ============================================================

-- Районы САО Москвы
CREATE TABLE districts (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(100) NOT NULL UNIQUE,
    code        VARCHAR(50),                          -- краткий код: aeroport, sokol ...
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Дворовые территории (адреса)
CREATE TABLE courtyards (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    district_id UUID NOT NULL REFERENCES districts(id),
    name        VARCHAR(500) NOT NULL,                 -- "Красноармейская ул. 26 к.2"
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(district_id, name)
);

-- ============================================================
-- 2. ПЛОЩАДКИ
-- ============================================================

CREATE TYPE site_type AS ENUM ('Детская площадка', 'Спортивная площадка');

CREATE TABLE sites (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    courtyard_id    UUID NOT NULL REFERENCES courtyards(id),
    type            site_type NOT NULL,
    area_m2         NUMERIC(10,2) NOT NULL,             -- площадь из KML (уже скорректирована)
    cleaning_type   VARCHAR(50) DEFAULT 'Ручная уборка',
    geometry        GEOMETRY(POLYGON, 4326) NOT NULL,   -- WGS84
    centroid        GEOMETRY(POINT, 4326)               -- авто-вычисляемый центр
        GENERATED ALWAYS AS (ST_Centroid(geometry)) STORED,
    kml_original_id VARCHAR(200),                       -- для обратной трассировки
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    assigned_inspector_id UUID,                          -- FK на users добавляется ниже (users объявлена позже)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ
);

CREATE INDEX idx_sites_type ON sites(type);
CREATE INDEX idx_sites_courtyard ON sites(courtyard_id);
CREATE INDEX idx_sites_geom ON sites USING GIST(geometry);

-- ============================================================
-- 3. ОБОРУДОВАНИЕ (на площадке)
-- ============================================================

CREATE TYPE equipment_type AS ENUM (
    'Качели', 'Горка', 'Турник', 'Песочница', 'Карусель',
    'Баскетбольное кольцо', 'Футбольные ворота', 'Тренажёр',
    'Скамейка', 'Урна', 'Ограждение', 'Покрытие', 'Прочее'
);

CREATE TABLE equipment (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    site_id     UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    type        equipment_type NOT NULL,
    name        VARCHAR(200),
    quantity    INT DEFAULT 1,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_equipment_site ON equipment(site_id);

-- ============================================================
-- 4. ПОЛЬЗОВАТЕЛИ
-- ============================================================

CREATE TYPE user_role AS ENUM (
    'inspector',    -- инспектор: проводит обходы, создаёт замечания, видит только свои записи
    'reviewer',     -- проверяющий: видит/меняет статус обходов и замечаний в своей зоне
                    -- (district_id задан — только этот район; NULL — весь округ)
    'admin'         -- администратор: без ограничения зоны, управляет пользователями
);

CREATE TABLE users (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    login          VARCHAR(50) NOT NULL UNIQUE,
    password_hash  VARCHAR(255) NOT NULL,
    full_name      VARCHAR(200) NOT NULL,
    role           user_role NOT NULL,
    district_id    UUID REFERENCES districts(id),     -- для inspector и reviewer; NULL у reviewer = весь округ
    phone          VARCHAR(20),
    is_active      BOOLEAN DEFAULT TRUE,
    must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
    is_developer   BOOLEAN NOT NULL DEFAULT FALSE,  -- доп. меню "Разработчик" в админ-панели
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Приглашения на регистрацию: админ заводит инвайт с ролью/районом, сам
-- пользователь по ссылке с токеном задаёт себе пароль (см. POST /auth/invites,
-- POST /auth/invites/{token}/complete).
CREATE TABLE user_invites (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    login        VARCHAR(50) NOT NULL UNIQUE,
    full_name    VARCHAR(200) NOT NULL,
    role         user_role NOT NULL,
    district_id  UUID REFERENCES districts(id),
    token_hash   VARCHAR(128) NOT NULL,
    created_by   UUID NOT NULL REFERENCES users(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at   TIMESTAMPTZ NOT NULL,
    used_at      TIMESTAMPTZ
);

CREATE INDEX idx_user_invites_token_hash ON user_invites(token_hash);

-- ============================================================
-- 5. ЧЕК-ЛИСТЫ
-- ============================================================

CREATE TABLE checklist_templates (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(200) NOT NULL,                  -- "Осмотр детской площадки"
    site_type   site_type,                              -- к какому типу площадки привязан
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE checklist_items (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    template_id     UUID NOT NULL REFERENCES checklist_templates(id) ON DELETE CASCADE,
    category        VARCHAR(200),                        -- "Покрытие", "Оборудование", "Ограждение"
    question        VARCHAR(500) NOT NULL,               -- "Целостность покрытия"
    sort_order      INT DEFAULT 0,
    is_critical     BOOLEAN DEFAULT FALSE,               -- критический пункт?
    requires_photo  BOOLEAN DEFAULT FALSE,               -- требуется ли фото
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,        -- FALSE = скрытый админом пункт, из новых обходов не показывается
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_checklist_items_template ON checklist_items(template_id);

-- ============================================================
-- 6. ОБХОДЫ
-- ============================================================

CREATE TYPE inspection_status AS ENUM (
    'planned',       -- запланирован
    'in_progress',   -- выполняется
    'completed',     -- без замечаний
    'issues_found',  -- есть замечания
    'critical'       -- критические замечания
);

CREATE TYPE inspection_type AS ENUM (
    'regular',       -- плановый
    'unscheduled',   -- внеплановый
    'control',       -- контрольный (после устранения)
    'seasonal'       -- сезонный
);

CREATE TABLE inspections (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    site_id         UUID NOT NULL REFERENCES sites(id),
    inspector_id    UUID NOT NULL REFERENCES users(id),
    template_id     UUID REFERENCES checklist_templates(id),
    type            inspection_type NOT NULL DEFAULT 'regular',
    status          inspection_status NOT NULL DEFAULT 'planned',
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    gps_lat         NUMERIC(9,6),                        -- фактическая геометка обходчика
    gps_lon         NUMERIC(9,6),
    comment         TEXT,                                -- комментарий инспектора
    reviewer_comment TEXT,                               -- комментарий проверяющего
    reviewed_by     UUID REFERENCES users(id),           -- кто проверил
    reviewed_at     TIMESTAMPTZ,                         -- когда проверил
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_inspections_site ON inspections(site_id);
CREATE INDEX idx_inspections_inspector ON inspections(inspector_id);
CREATE INDEX idx_inspections_status ON inspections(status);
CREATE INDEX idx_inspections_date ON inspections(created_at);

-- ============================================================
-- 7. ОТВЕТЫ ПО ЧЕК-ЛИСТУ
-- ============================================================

CREATE TYPE checklist_result AS ENUM ('ok', 'defect', 'not_applicable', 'not_checked');

CREATE TABLE checklist_answers (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    inspection_id   UUID NOT NULL REFERENCES inspections(id) ON DELETE CASCADE,
    checklist_item_id UUID NOT NULL REFERENCES checklist_items(id),
    result          checklist_result NOT NULL,
    comment         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(inspection_id, checklist_item_id)
);

CREATE INDEX idx_checklist_answers_inspection ON checklist_answers(inspection_id);

-- ============================================================
-- 8. ФОТОГРАФИИ
-- ============================================================

CREATE TYPE photo_target AS ENUM ('inspection', 'issue', 'equipment', 'checklist_answer', 'issue_fix');

CREATE TABLE photos (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    target_type     photo_target NOT NULL,
    inspection_id   UUID REFERENCES inspections(id) ON DELETE CASCADE,
    issue_id        UUID,                                -- FK added below
    equipment_id    UUID REFERENCES equipment(id),
    checklist_answer_id UUID REFERENCES checklist_answers(id) ON DELETE SET NULL,
    storage_path    VARCHAR(500) NOT NULL,               -- путь в S3/MinIO
    thumbnail_path  VARCHAR(500),                        -- превью
    gps_lat         NUMERIC(9,6),
    gps_lon         NUMERIC(9,6),
    taken_at        TIMESTAMPTZ,                         -- EXIF-дата съёмки
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_photos_inspection ON photos(inspection_id);
CREATE INDEX idx_photos_issue ON photos(issue_id);

-- ============================================================
-- 9. ЗАМЕЧАНИЯ / ДЕФЕКТЫ
-- ============================================================

CREATE TYPE issue_criticality AS ENUM ('low', 'medium', 'high', 'critical');
CREATE TYPE issue_status AS ENUM (
    'open',            -- открыто
    'assigned',        -- назначен ответственный
    'in_work',         -- в работе
    'fixed',           -- устранено
    'control',         -- на контроле
    'closed',          -- закрыто
    'overdue',         -- просрочено
    'revision_needed'  -- возвращено на доработку проверяющим
);

CREATE TABLE issues (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    inspection_id   UUID NOT NULL REFERENCES inspections(id),
    site_id         UUID NOT NULL REFERENCES sites(id),
    checklist_answer_id UUID REFERENCES checklist_answers(id) ON DELETE SET NULL, -- пункт чек-листа, породивший замечание автоматически (NULL — заведено вручную)
    title           VARCHAR(300) NOT NULL,
    description     TEXT,
    criticality     issue_criticality NOT NULL DEFAULT 'medium',
    status          issue_status NOT NULL DEFAULT 'open',
    assigned_to     UUID REFERENCES users(id),
    due_date        DATE,                                 -- срок устранения
    fixed_at        TIMESTAMPTZ,
    reviewer_comment TEXT,                                -- комментарий проверяющего (напр. причина возврата на доработку)
    fix_comment     TEXT,                                 -- описание исправления от того, кто устранял
    created_by      UUID NOT NULL REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ
);

CREATE INDEX idx_issues_inspection ON issues(inspection_id);
CREATE INDEX idx_issues_site ON issues(site_id);
CREATE INDEX idx_issues_status ON issues(status);
CREATE UNIQUE INDEX ux_issues_checklist_answer_id ON issues(checklist_answer_id) WHERE checklist_answer_id IS NOT NULL;
CREATE INDEX idx_issues_criticality ON issues(criticality);
CREATE INDEX idx_issues_assigned ON issues(assigned_to);

-- FK для photos.issue_id
ALTER TABLE photos ADD CONSTRAINT fk_photos_issue
    FOREIGN KEY (issue_id) REFERENCES issues(id) ON DELETE SET NULL;

-- FK для sites.assigned_inspector_id
ALTER TABLE sites ADD CONSTRAINT fk_sites_assigned_inspector
    FOREIGN KEY (assigned_inspector_id) REFERENCES users(id) ON DELETE SET NULL;
CREATE INDEX idx_sites_assigned_inspector ON sites(assigned_inspector_id);

-- ============================================================
-- 10. ИСТОРИЯ СТАТУСОВ ЗАМЕЧАНИЙ
-- ============================================================

CREATE TABLE issue_status_history (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    issue_id    UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    old_status  issue_status,
    new_status  issue_status NOT NULL,
    changed_by  UUID NOT NULL REFERENCES users(id),
    comment     TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_issue_history_issue ON issue_status_history(issue_id);

-- ============================================================
-- 11. ЖУРНАЛ АУДИТА
-- ============================================================

CREATE TABLE audit_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
    action      VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id   VARCHAR(100),
    details     TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 12. ЗАПОЛНЕНИЕ СПРАВОЧНИКА РАЙОНОВ
-- ============================================================

INSERT INTO districts (name, code) VALUES
    ('Аэропорт', 'aeroport'),
    ('Беговой', 'begovoy'),
    ('Бескудниковский', 'beskudnikovskiy'),
    ('Войковский', 'voykovskiy'),
    ('Восточное Дегунино', 'vostochnoe_degunnino'),
    ('Головинский', 'golovinskiy'),
    ('Дмитровский', 'dmitrovskiy'),
    ('Западное Дегунино', 'zapadnoe_degunnino'),
    ('Коптево', 'koptevo'),
    ('Левобережный', 'levoberezhniy'),
    ('Молжаниновский', 'molzhaninovskiy'),
    ('Савёловский', 'savelovskiy'),
    ('Сокол', 'sokol'),
    ('Тимирязевский', 'timiryazevskiy'),
    ('Ховрино', 'khovrino'),
    ('Хорошевский', 'khoroshevskiy'),
    ('Неизвестный район', 'unknown');   -- для 425 объектов без района

-- ============================================================
-- 13. СТАНДАРТНЫЙ ЧЕК-ЛИСТ (MVP)
-- ============================================================

INSERT INTO checklist_templates (id, name, site_type) VALUES
    ('c0000000-0000-0000-0000-000000000001', 'Осмотр детской площадки', 'Детская площадка'),
    ('c0000000-0000-0000-0000-000000000002', 'Осмотр спортивной площадки', 'Спортивная площадка');

INSERT INTO checklist_items (template_id, category, question, sort_order, is_critical, requires_photo) VALUES
    -- Детская площадка
    ('c0000000-0000-0000-0000-000000000001', 'Покрытие', 'Целостность покрытия (нет ям, выбоин)', 1, TRUE, FALSE),
    ('c0000000-0000-0000-0000-000000000001', 'Покрытие', 'Отсутствие посторонних предметов и мусора', 2, FALSE, FALSE),
    ('c0000000-0000-0000-0000-000000000001', 'Оборудование', 'Устойчивость и крепление качелей', 3, TRUE, FALSE),
    ('c0000000-0000-0000-0000-000000000001', 'Оборудование', 'Целостность горки (ступени, скат, поручни)', 4, TRUE, FALSE),
    ('c0000000-0000-0000-0000-000000000001', 'Оборудование', 'Состояние песочницы (чистота, ограждение)', 5, FALSE, FALSE),
    ('c0000000-0000-0000-0000-000000000001', 'Оборудование', 'Целостность карусели', 6, TRUE, FALSE),
    ('c0000000-0000-0000-0000-000000000001', 'МАФ', 'Состояние скамеек', 7, FALSE, FALSE),
    ('c0000000-0000-0000-0000-000000000001', 'МАФ', 'Состояние урн', 8, FALSE, FALSE),
    ('c0000000-0000-0000-0000-000000000001', 'Ограждение', 'Целостность ограждения', 9, TRUE, FALSE),
    ('c0000000-0000-0000-0000-000000000001', 'Общий вид', 'Фото общего вида площадки', 10, FALSE, TRUE),
    -- Спортивная площадка
    ('c0000000-0000-0000-0000-000000000002', 'Покрытие', 'Целостность покрытия (резина, асфальт)', 1, TRUE, FALSE),
    ('c0000000-0000-0000-0000-000000000002', 'Покрытие', 'Отсутствие посторонних предметов и мусора', 2, FALSE, FALSE),
    ('c0000000-0000-0000-0000-000000000002', 'Оборудование', 'Состояние ворот / баскетбольных колец', 3, TRUE, FALSE),
    ('c0000000-0000-0000-0000-000000000002', 'Оборудование', 'Целостность тренажёров', 4, TRUE, FALSE),
    ('c0000000-0000-0000-0000-000000000002', 'МАФ', 'Состояние скамеек', 5, FALSE, FALSE),
    ('c0000000-0000-0000-0000-000000000002', 'Ограждение', 'Целостность ограждения', 6, TRUE, FALSE),
    ('c0000000-0000-0000-0000-000000000002', 'Общий вид', 'Фото общего вида площадки', 7, FALSE, TRUE);

-- ============================================================
-- 14. ОБРАЩЕНИЯ ГРАЖДАН/СОТРУДНИКОВ (публичная веб-форма, без авторизации)
-- ============================================================

CREATE TYPE feedback_status AS ENUM ('new', 'in_review', 'resolved', 'dismissed');
-- site — жалоба по конкретной площадке/двору; app — техническая проблема
-- с самим приложением (не заходит, баг, что-то не отображается); other —
-- всё остальное. Определяет, какие поля формы показывает фронтенд.
CREATE TYPE feedback_report_type AS ENUM ('site', 'app', 'other');

CREATE TABLE feedback_reports (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_type    feedback_report_type NOT NULL DEFAULT 'site',
    full_name      VARCHAR(200),
    phone          VARCHAR(20),
    location_text  VARCHAR(500),          -- адрес/площадка ИЛИ где возникла техпроблема — свободный текст
    message        TEXT NOT NULL,
    status         feedback_status NOT NULL DEFAULT 'new',
    admin_comment  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at    TIMESTAMPTZ
);

CREATE INDEX idx_feedback_reports_status ON feedback_reports(status);
CREATE INDEX idx_feedback_reports_created ON feedback_reports(created_at);
CREATE INDEX idx_feedback_reports_type ON feedback_reports(report_type);

-- Фото или файлы (списки и т.п.), приложенные к обращению — не Photo, та
-- привязана к обходу/замечанию/оборудованию и подразумевает именно фото.
CREATE TABLE feedback_attachments (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    feedback_report_id  UUID NOT NULL REFERENCES feedback_reports(id) ON DELETE CASCADE,
    storage_path        VARCHAR(500) NOT NULL,
    original_filename   VARCHAR(255),
    content_type        VARCHAR(100),
    size_bytes          INT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_feedback_attachments_report ON feedback_attachments(feedback_report_id);
