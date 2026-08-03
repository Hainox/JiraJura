-- ============================================================
-- SEED-данные: тестовый пользователь
-- ============================================================

-- Пароль: admin123
INSERT INTO users (login, password_hash, full_name, role, is_active)
VALUES (
    'admin',
    '$2b$12$p9sdkXbiFFkWtQv5e81cP.rv1TkBThZouKjalZzEGwuSBDCx3QPkS',
    'Администратор Системы',
    'system_admin',
    TRUE
);
