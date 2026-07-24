"""Tests for the two deliberately-distinct 'active as of a cutoff' forms."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hiero_analytics.domain.recency import is_active, is_active_since


def test_is_active_truncates_partial_days():
    """The day-difference form truncates partial days (matches timedelta.days)."""
    now = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
    # 30 days and 23 hours ago -> .days == 30, still within a 30-day window.
    assert is_active(now - timedelta(days=30, hours=23), now, within_days=30) is True
    # 31 full days ago -> outside.
    assert is_active(now - timedelta(days=31), now, within_days=30) is False


def test_is_active_never_seen_is_inactive_and_none_window_counts_any_activity():
    """None last_active is never active; within_days=None accepts any recorded activity."""
    now = datetime(2026, 1, 10, tzinfo=UTC)
    assert is_active(None, now, within_days=30) is False
    assert is_active(None, now, within_days=None) is False
    assert is_active(now - timedelta(days=9999), now, within_days=None) is True


def test_is_active_since_compares_timestamps_exactly():
    """The cutoff form compares timestamps exactly, with no day truncation."""
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    assert is_active_since(cutoff, cutoff) is True  # boundary is inclusive
    assert is_active_since(cutoff - timedelta(seconds=1), cutoff) is False
    assert is_active_since(None, cutoff) is False
