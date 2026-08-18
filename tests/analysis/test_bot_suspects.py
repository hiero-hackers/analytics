"""Tests for the bot-suspects review-table transform."""

from __future__ import annotations

from datetime import UTC, datetime

from hiero_analytics.analysis.bot_suspects import build_bot_suspects
from hiero_analytics.data_sources.models import ContributorActivityRecord

REPO = "hiero-hackers/analytics"


def _activity(actor: str) -> ContributorActivityRecord:
    return ContributorActivityRecord(
        repo=REPO,
        activity_type="authored_pull_request",
        actor=actor,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        target_type="pull_request",
        target_number=1,
        target_author=actor,
    )


def test_flags_logins_with_a_weak_signal():
    """A contributor login matching a weak signal is flagged with which one fired."""
    suspects = build_bot_suspects([_activity("hiero-automation"), _activity("sdk-release-ci")])

    assert list(suspects["login"]) == ["hiero-automation", "sdk-release-ci"]
    assert list(suspects["signal"]) == ["automation", "ci"]


def test_excludes_clean_human_logins():
    """A login tripping no weak signal never appears in the suspects table."""
    suspects = build_bot_suspects([_activity("alice"), _activity("bob")])

    assert suspects.empty
    assert list(suspects.columns) == ["login", "signal"]


def test_excludes_logins_is_bot_login_already_catches():
    """Named/suffixed automation accounts are resolved already, not suspects."""
    suspects = build_bot_suspects([_activity("dependabot[bot]"), _activity("renovate")])

    assert suspects.empty


def test_dedupes_case_insensitively():
    """The same contributor showing up with different casing is one row."""
    suspects = build_bot_suspects([_activity("Hiero-Automation"), _activity("hiero-automation")])

    assert len(suspects) == 1
    assert suspects.iloc[0]["login"] == "hiero-automation"


def test_ignores_records_with_no_actor():
    """A record with a falsy actor doesn't blow up the sweep."""
    suspects = build_bot_suspects([_activity("")])

    assert suspects.empty


def test_empty_input_returns_empty_frame_with_schema():
    """No records still produces a stable-schema empty frame, not a crash."""
    suspects = build_bot_suspects([])

    assert suspects.empty
    assert list(suspects.columns) == ["login", "signal"]


def test_sorted_alphabetically_by_login():
    """Rows come out sorted so the CSV is stable and easy to scan."""
    suspects = build_bot_suspects([_activity("sdk-release-ci"), _activity("hiero-automation")])

    assert list(suspects["login"]) == ["hiero-automation", "sdk-release-ci"]
