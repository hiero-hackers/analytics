"""Tests for the shared record (de)serialization helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hiero_analytics.data_sources.serialization import parse_github_datetime


def test_parse_github_datetime_normalizes_trailing_z():
    """A trailing 'Z' is parsed as UTC."""
    assert parse_github_datetime("2024-01-02T03:04:05Z") == datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)


def test_parse_github_datetime_returns_none_for_missing_or_nonstring():
    """Absent / non-string input is an absent optional field, not an error."""
    assert parse_github_datetime(None) is None
    assert parse_github_datetime("") is None
    assert parse_github_datetime(12345) is None


def test_parse_github_datetime_lenient_by_default_strict_on_request():
    """A malformed timestamp returns None normally, but raises under strict=True."""
    assert parse_github_datetime("not-a-date") is None
    with pytest.raises(ValueError, match="Invalid isoformat|not-a-date"):
        parse_github_datetime("not-a-date", strict=True)
