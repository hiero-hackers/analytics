"""Tests for automation-account (bot) identification."""

from __future__ import annotations

from hiero_analytics.domain.bots import bot_suspect_signal, is_bot_login


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


def test_suspect_signal_catches_unsuffixed_automation_logins():
    """Logins is_bot_login misses because they carry no suffix still trip a suspect signal."""
    assert bot_suspect_signal("hiero-automation") == "automation"
    assert bot_suspect_signal("sdk-release-ci") == "ci"


def test_suspect_signal_catches_bot_as_a_non_suffix_substring():
    """'bot' appearing mid-login (not as the '-bot'/'[bot]' suffix) still fires."""
    assert bot_suspect_signal("botrunner") == "bot"
    assert bot_suspect_signal("sdk-bot-helper") == "bot"


def test_suspect_signal_prefers_the_more_specific_match():
    """A login matching both 'automation' and its substring 'auto' reports the more specific one."""
    assert bot_suspect_signal("hiero-automation") == "automation"


def test_suspect_signal_is_none_for_already_excluded_bot_logins():
    """A login is_bot_login already excludes is not also a suspect — it's resolved, not pending review."""
    assert bot_suspect_signal("dependabot[bot]") is None
    assert bot_suspect_signal("renovate") is None


def test_suspect_signal_is_none_for_clean_human_logins():
    """A login with none of the weak signals is left alone."""
    assert bot_suspect_signal("alice") is None
    assert bot_suspect_signal("robert-downey") is None
