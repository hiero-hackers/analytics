"""Shared recency semantics: what "active as of a cutoff" means project-wide.

Two canonical forms exist and they are deliberately NOT interchangeable: the
day-difference form truncates partial days (``(now - last_active).days``),
while the cutoff form compares timestamps exactly. Each call site keeps its
historical form; both live here so "active" is defined in one place.
"""

from __future__ import annotations

from datetime import datetime


def is_active(last_active: datetime | None, now: datetime, within_days: int | None) -> bool:
    """Day-difference form: active when last seen at most ``within_days`` ago.

    ``None`` ``last_active`` (never seen) is never active; ``within_days=None``
    counts any recorded activity. Partial days truncate, matching
    ``timedelta.days``.
    """
    if last_active is None:
        return False
    return within_days is None or (now - last_active).days <= within_days


def is_active_since(last_active: datetime | None, cutoff: datetime) -> bool:
    """Cutoff form: active when last seen at or after ``cutoff``."""
    return last_active is not None and last_active >= cutoff
