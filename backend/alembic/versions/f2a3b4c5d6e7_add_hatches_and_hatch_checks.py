"""add hatches, hatch_checks and issue category «Люки»

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-30
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS / ON CONFLICT — schema.sql (свежие инсталляции) уже
    # содержит эти таблицы и категорию, upgrade head на такой БД проходит
    # эту ревизию повторно поверх уже применённого schema.sql.
    op.execute("""
        CREATE TABLE IF NOT EXISTS hatches (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            site_id       UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
            number        VARCHAR(20) NOT NULL,
            owner         VARCHAR(150),
            location_note VARCHAR(300),
            point         GEOMETRY(POINT, 4326),
            external_id   VARCHAR(100) UNIQUE,
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (site_id, number)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_hatches_site ON hatches(site_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS hatch_checks (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            inspection_id UUID NOT NULL REFERENCES inspections(id) ON DELETE CASCADE,
            hatch_id      UUID NOT NULL REFERENCES hatches(id) ON DELETE CASCADE,
            state         VARCHAR(20) NOT NULL
                          CHECK (state IN ('ok', 'shifted', 'damaged', 'missing', 'sink')),
            fenced        BOOLEAN,
            owner_ticket  VARCHAR(100),
            comment       TEXT,
            issue_id      UUID REFERENCES issues(id) ON DELETE SET NULL,
            checked_by    UUID NOT NULL REFERENCES users(id),
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ,
            UNIQUE (inspection_id, hatch_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_hatch_checks_hatch ON hatch_checks(hatch_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_hatch_checks_created ON hatch_checks(created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_hatch_checks_issue ON hatch_checks(issue_id)")

    op.execute("""
        INSERT INTO issue_categories (name, sort_order) VALUES ('Люки', 45)
        ON CONFLICT (name) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS hatch_checks")
    op.execute("DROP TABLE IF EXISTS hatches")
    # Категорию удаляем только если на неё ещё ничего не ссылается:
    # issues.category_id NOT NULL, и уже заведённые замечания «Люки» —
    # реальная история устранения, их нельзя терять ради отката схемы.
    op.execute("""
        DELETE FROM issue_categories c
        WHERE c.name = 'Люки'
          AND NOT EXISTS (SELECT 1 FROM issues i WHERE i.category_id = c.id)
          AND NOT EXISTS (SELECT 1 FROM checklist_items ci WHERE ci.category_id = c.id)
    """)
