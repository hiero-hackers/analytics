"""Shared time-period definitions for windowed activity analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class Period:
    """A named rolling activity window; ``days=None`` means all recorded time."""

    key: str
    label: str
    days: int | None
    default: bool = False

    def cutoff(self, now: datetime) -> datetime | None:
        """Return the inclusive lower bound for this period."""
        return None if self.days is None else now - timedelta(days=self.days)

    def filename(self, stem: str) -> str:
        """Return the conventional CSV filename for this period."""
        return f"{stem}_{self.key}.csv"


# The dashboard's one period vocabulary: Week, 1 month, 1 year — plus the
# all-time base every table already is (the period selector's null state, so no
# "all" entry here; emitting one duplicated every row and doubled the tab).
# Chart span tabs use the same three labels so tables and charts never offer
# different windows for the same idea. Windows that are *semantic thresholds*
# rather than filters (ROLE_ACTIVE_DAYS' 90-day active/quiet line,
# GONE_DARK_DAYS) deliberately do not live here.
ACTIVITY_PERIODS = (
    Period("7d", "Week", 7),
    Period("30d", "1 month", 30, default=True),
    Period("365d", "1 year", 365),
)

# The period whose tab opens active on the dashboard.
DEFAULT_ACTIVITY_PERIOD = next(period for period in ACTIVITY_PERIODS if period.default)
