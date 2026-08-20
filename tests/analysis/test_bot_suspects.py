"""Tests for the bot-suspects review-table transform."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml

from hiero_analytics.analysis.affiliation import AFFILIATIONS_PATH
from hiero_analytics.analysis.bot_suspects import build_bot_suspects, load_dismissed_suspects
from hiero_analytics.data_sources.models import ContributorActivityRecord
from hiero_analytics.domain.bots import bot_suspect_signal

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
    suspects = build_bot_suspects([_activity("hiero-automation"), _activity("sdk-release-ci")], dismissed=set())

    assert list(suspects["login"]) == ["hiero-automation", "sdk-release-ci"]
    assert list(suspects["signal"]) == ["automation", "ci"]


def test_excludes_clean_human_logins():
    """A login tripping no weak signal never appears in the suspects table."""
    suspects = build_bot_suspects([_activity("alice"), _activity("bob")], dismissed=set())

    assert suspects.empty
    assert list(suspects.columns) == ["login", "signal"]


def test_excludes_logins_is_bot_login_already_catches():
    """Named/suffixed automation accounts are resolved already, not suspects."""
    suspects = build_bot_suspects([_activity("dependabot[bot]"), _activity("renovate")], dismissed=set())

    assert suspects.empty


def test_dedupes_case_insensitively():
    """The same contributor showing up with different casing is one row."""
    suspects = build_bot_suspects([_activity("Hiero-Automation"), _activity("hiero-automation")], dismissed=set())

    assert len(suspects) == 1
    assert suspects.iloc[0]["login"] == "hiero-automation"


def test_ignores_records_with_no_actor():
    """A record with a falsy actor doesn't blow up the sweep."""
    suspects = build_bot_suspects([_activity("")], dismissed=set())

    assert suspects.empty


def test_empty_input_returns_empty_frame_with_schema():
    """No records still produces a stable-schema empty frame, not a crash."""
    suspects = build_bot_suspects([], dismissed=set())

    assert suspects.empty
    assert list(suspects.columns) == ["login", "signal"]


def test_sorted_alphabetically_by_login():
    """Rows come out sorted so the CSV is stable and easy to scan."""
    suspects = build_bot_suspects([_activity("sdk-release-ci"), _activity("hiero-automation")], dismissed=set())

    assert list(suspects["login"]) == ["hiero-automation", "sdk-release-ci"]


def test_dismissed_logins_are_skipped():
    """A login a maintainer already confirmed is a real person doesn't reappear."""
    suspects = build_bot_suspects(
        [_activity("hiero-automation"), _activity("cijujohn")],
        dismissed={"cijujohn"},
    )

    assert list(suspects["login"]) == ["hiero-automation"]


def test_dismissed_lookup_is_case_insensitive():
    """Dismissals match regardless of the casing GitHub returns for the actor."""
    suspects = build_bot_suspects([_activity("CijuJohn")], dismissed={"cijujohn"})

    assert suspects.empty


def test_load_dismissed_suspects_parses_bare_logins(tmp_path: Path):
    """One lowercase login per line; comments and blank lines are ignored."""
    dismissals = tmp_path / "bot_suspect_dismissals.yaml"
    dismissals.write_text(
        "# header comment\n\ncijujohn  # reviewed by someone, human login\nJoshMarinacci # trailing comment\n",
        encoding="utf-8",
    )

    assert load_dismissed_suspects(dismissals) == {"cijujohn", "joshmarinacci"}


def test_load_dismissed_suspects_missing_file_returns_empty_set(tmp_path: Path):
    """A missing dismissals file just means nothing's been dismissed yet, not a crash."""
    assert load_dismissed_suspects(tmp_path / "does_not_exist.yaml") == set()


def test_signal_false_positive_rate_against_real_contributor_logins():
    """Regression guard: the heuristic should stay rare against real logins.

    affiliations.yaml is the project's actual curated contributor list, so it
    doubles as a sanity check for the suspect signal per review feedback on
    #328 — this fails loudly if a future change to SUSPECT_SIGNALS makes the
    heuristic noisy again, rather than that only being caught by a maintainer
    skimming a much longer bot_suspects.csv by hand.
    """
    real_logins = list(yaml.safe_load(AFFILIATIONS_PATH.read_text(encoding="utf-8")).keys())
    assert len(real_logins) > 100  # sanity: this really is the full curated list

    flagged = [login for login in real_logins if bot_suspect_signal(login)]
    # Not zero — "ci" as a real prefix/suffix is an accepted tradeoff (see
    # bot_suspect_signal's docstring) — but should stay a handful, not a flood.
    assert len(flagged) <= 5, f"suspect signal is flagging real logins broadly: {flagged}"
