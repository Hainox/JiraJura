"""relink legacy checklist photos to unified issues

Revision ID: d2e3f4a5b6c7
Revises: c0d1e2f3a4b5
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "c0d1e2f3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A defect answer has at most one linked issue (ux_issues_checklist_answer_id).
    # Keep checklist_answer_id as immutable historical provenance while making the
    # source image visible from the one operational record, Issue.
    op.execute("""
        UPDATE photos AS photo
        SET issue_id = issue.id,
            target_type = 'issue'::photo_target
        FROM issues AS issue
        WHERE photo.target_type = 'checklist_answer'::photo_target
          AND photo.checklist_answer_id = issue.checklist_answer_id
          AND photo.issue_id IS NULL
    """)
    # The remaining checklist photos document the inspection itself (not a
    # violation), for example its required general-view image. Preserve their
    # links and make them readable through the inspection photo path.
    op.execute("""
        UPDATE photos
        SET target_type = 'inspection'::photo_target
        WHERE target_type = 'checklist_answer'::photo_target
          AND issue_id IS NULL
    """)


def downgrade() -> None:
    # This migration is deliberately forward-only: reverting target types would
    # lose the distinction between original issue evidence and general photos.
    pass
