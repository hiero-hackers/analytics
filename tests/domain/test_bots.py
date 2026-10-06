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


def test_suspect_signal_catches_bot_as_its_own_token():
    """'bot' fires when it's a whole token on its own, not the '-bot'/'[bot]' suffix."""
    assert bot_suspect_signal("sdk-bot-helper") == "bot"
    assert bot_suspect_signal("hiero-bot-prod") == "bot"


def test_suspect_signal_ignores_a_signal_glued_onto_a_longer_word():
    """A signal that isn't a standalone token — prefix, suffix, or buried mid-word — doesn't fire.

    Checked against this project's own 256 real contributor logins, the
    earlier prefix/suffix-anchored version flagged real people purely because
    a signal's letters happened to start or end a token: "cijujohn" and
    "joshmarinacci" via "ci", and "mrswastik-robot" (a real, active
    contributor) via "bot", since "robot" ends in "bot". All were false
    positives; none were automation accounts. Requiring an exact token match
    rules all of these out.
    """
    assert bot_suspect_signal("viniciusjssouza") is None  # "ci" buried mid-word
    assert bot_suspect_signal("marcia") is None  # "ci" buried mid-word
    assert bot_suspect_signal("cijujohn") is None  # "ci" as a token prefix only
    assert bot_suspect_signal("joshmarinacci") is None  # "ci" as a token suffix only
    assert bot_suspect_signal("botrunner") is None  # "bot" as a token prefix only
    assert bot_suspect_signal("mrswastik-robot") is None  # "bot" as a suffix of "robot"


def test_suspect_signal_prefers_the_more_specific_token():
    """When a login has multiple tokens matching different signals, the first match by priority order wins."""
    assert bot_suspect_signal("automation-ci") == "automation"


def test_suspect_signal_is_none_for_already_excluded_bot_logins():
    """A login is_bot_login already excludes is not also a suspect — it's resolved, not pending review."""
    assert bot_suspect_signal("dependabot[bot]") is None
    assert bot_suspect_signal("renovate") is None


def test_suspect_signal_is_none_for_clean_human_logins():
    """A login with none of the weak signals is left alone."""
    assert bot_suspect_signal("alice") is None
    assert bot_suspect_signal("robert-downey") is None
