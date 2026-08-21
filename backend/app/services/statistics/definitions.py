"""Canonical definitions used by every statistics v2 consumer."""

from decimal import Decimal, ROUND_HALF_UP

DONE_STATUSES = ("completed", "issues_found", "critical")
OPEN_STATUSES = ("open",)
IN_WORK_STATUSES = ("assigned", "in_work")
ON_CHECK_STATUSES = ("fixed", "control")
REVISION_STATUSES = ("revision_needed",)
OVERDUE_STATUSES = ("open", "assigned", "in_work", "revision_needed")
NIL_UUID = "00000000-0000-0000-0000-000000000000"


def percent(numerator: int, denominator: int) -> int:
    """Integer percent using the product-approved ROUND_HALF_UP rule."""
    if numerator < 0 or denominator < 0:
        raise ValueError("statistics values must be non-negative")
    if denominator == 0:
        return 0
    return int(
        (Decimal(numerator) * Decimal(100) / Decimal(denominator)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
