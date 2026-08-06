"""Tests for shared activity period definitions."""

from datetime import UTC, datetime

from hiero_analytics.domain.periods import ACTIVITY_PERIODS, DEFAULT_ACTIVITY_PERIOD


def test_the_period_vocabulary_is_week_month_year():
    """One vocabulary everywhere.

    Tables and chart span tabs offer the same windows under the same labels,
    so no surface filters differently from another. All-time is deliberately
    absent — it is every table's base rows and the selector's null state.
    """
    assert [(p.key, p.label, p.days) for p in ACTIVITY_PERIODS] == [
        ("7d", "Week", 7),
        ("30d", "1 month", 30),
        ("365d", "1 year", 365),
    ]


def test_activity_periods_have_stable_cutoffs_and_filenames():
    """Rolling periods expose a cutoff and a conventional CSV filename."""
    now = datetime(2026, 7, 21, tzinfo=UTC)
    periods = {period.key: period for period in ACTIVITY_PERIODS}

    assert periods["30d"].cutoff(now) == datetime(2026, 6, 21, tzinfo=UTC)
    assert periods["30d"].filename("team_activity_summary") == "team_activity_summary_30d.csv"


def test_exactly_one_period_is_the_dashboard_default():
    """Tables open on the 1-month window.

    Recent enough to be current, wide enough not to be noise.
    """
    assert DEFAULT_ACTIVITY_PERIOD.key == "30d"
    assert sum(period.default for period in ACTIVITY_PERIODS) == 1
