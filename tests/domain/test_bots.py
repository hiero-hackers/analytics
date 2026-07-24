"""Tests for automation-account (bot) identification."""

from __future__ import annotations

from hiero_analytics.domain.bots import is_bot_login


def test_suffixed_bot_logins_are_detected():
    """The ``[bot]`` and ``-bot`` suffixes mark a login as automation, case-insensitively."""
    assert is_bot_login("dependabot[bot]") is True
    assert is_bot_login("some-release-bot") is True
    assert is_bot_login("SOME-RELEASE-BOT") is True


def test_named_bots_without_a_suffix_are_detected():
    """Known automation accounts whose login carries no suffix are still caught."""
    assert is_bot_login("dependabot") is True
    assert is_bot_login("github-actions") is True
    assert is_bot_login("Renovate") is True  # case-insensitive name-list match


def test_people_logins_are_not_bots():
    """An ordinary human login is not flagged."""
    assert is_bot_login("alice") is False
    assert is_bot_login("robert-downey") is False  # '-bot' must be a suffix, not a substring
