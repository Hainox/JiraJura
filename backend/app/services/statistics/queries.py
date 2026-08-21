"""Reusable SQL expressions for grouped statistics queries."""

from sqlalchemy import func

from app.models import Issue
from .definitions import IN_WORK_STATUSES, ON_CHECK_STATUSES, OVERDUE_STATUSES


def count_if(condition):
    return func.count().filter(condition)


def issue_bucket_columns(today):
    return (
        func.count(Issue.id).label("found"),
        count_if(Issue.status == "closed").label("closed"),
        count_if(Issue.status.in_(ON_CHECK_STATUSES)).label("on_check"),
        count_if(Issue.status == "revision_needed").label("revision"),
        count_if(Issue.status.in_(IN_WORK_STATUSES)).label("in_work"),
        count_if(Issue.status == "open").label("open"),
        count_if(
            Issue.status.in_(OVERDUE_STATUSES)
            & Issue.due_date.is_not(None)
            & (Issue.due_date < today)
        ).label("overdue"),
    )
