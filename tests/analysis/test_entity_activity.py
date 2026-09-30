"""Per-window repository and contributor activity, counted from the events."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from hiero_analytics.analysis.contributor_activity_profile import combined_activity_events
from hiero_analytics.analysis.entity_activity import (
    contributor_activity,
    monthly_activity,
    repo_activity,
    repo_contributor_activity,
)
from hiero_analytics.data_sources.models import ContributorActivityRecord, IssueTimelineEventRecord

NOW = datetime(2026, 7, 1, 12, tzinfo=UTC)
WINDOWS = [("all", None), ("7d", NOW - timedelta(days=7)), ("30d", NOW - timedelta(days=30))]


def _act(repo, actor, activity_type, days_ago, number=1, target_author=None):
    return ContributorActivityRecord(
        repo=f"org/{repo}",
        activity_type=activity_type,
        actor=actor,
        occurred_at=NOW - timedelta(days=days_ago),
        target_type="issue" if activity_type == "authored_issue" else "pull_request",
        target_number=number,
        target_author=target_author or actor,
    )


def _label(repo, actor, days_ago, event_type="labeled"):
    return IssueTimelineEventRecord(
        repo=f"org/{repo}",
        issue_number=9,
        event_type=event_type,
        occurred_at=NOW - timedelta(days=days_ago),
        label="bug",
        actor=actor,
    )


@pytest.fixture
def events() -> pd.DataFrame:
    """Tracked events across two repositories, with a bot and a label removal mixed in."""
    records = [
        # alice: a PR 2 days ago in sdk, an issue 20 days ago in sdk, a PR 100 days ago in docs.
        _act("sdk", "alice", "authored_pull_request", 2, number=1),
        _act("sdk", "alice", "authored_issue", 20, number=5),
        _act("docs", "alice", "authored_pull_request", 100, number=2),
        # bob reviews and merges alice's sdk PR: the merge is bob's, not alice's.
        _act("sdk", "bob", "reviewed_pull_request", 1, number=1, target_author="alice"),
        _act("sdk", "bob", "merged_pull_request", 1, number=1, target_author="alice"),
        # A bot's action is never a contributor's.
        _act("sdk", "dependabot[bot]", "authored_pull_request", 1, number=3),
    ]
    labels = [
        _label("sdk", "carol", 3),
        # Removing a label is not applying one.
        _label("sdk", "carol", 3, event_type="unlabeled"),
        _label("docs", "carol", 40),
    ]
    return combined_activity_events(records, labels)


def _row(frame: pd.DataFrame, **match) -> dict:
    selected = frame
    for key, value in match.items():
        selected = selected[selected[key] == value]
    assert len(selected) == 1, match
    return selected.iloc[0].to_dict()


def test_repository_counts_each_window_from_its_own_events(events):
    """Each window counts only the events inside it, by type."""
    table = repo_activity(events, WINDOWS)

    sdk_all = _row(table, repo="org/sdk", period="all")
    assert (sdk_all["prs_opened"], sdk_all["reviews_given"], sdk_all["merges_done"]) == (1, 1, 1)
    assert (sdk_all["issues_opened"], sdk_all["labels_applied"], sdk_all["total_actions"]) == (1, 1, 5)
    assert sdk_all["active_contributors"] == 3  # alice, bob, carol; not the bot

    sdk_week = _row(table, repo="org/sdk", period="7d")
    # The issue (20 days ago) is outside the week; the label (3 days) is inside.
    assert (sdk_week["issues_opened"], sdk_week["labels_applied"], sdk_week["total_actions"]) == (0, 1, 4)
    assert sdk_week["active_contributors"] == 3

    # docs had a PR 100 days ago and a label 40 days ago: nothing in the last month.
    assert table[(table["repo"] == "org/docs") & (table["period"] == "30d")].empty
    assert _row(table, repo="org/docs", period="all")["active_contributors"] == 2


def test_active_contributors_are_distinct_people_not_a_sum(events):
    """Active contributors are distinct people, while totals still add up per person."""
    # Two actions by the same person in one repository count one active contributor.
    table = repo_activity(events, WINDOWS)
    assert _row(table, repo="org/sdk", period="30d")["active_contributors"] == 3
    per_person = repo_contributor_activity(events, WINDOWS)
    scoped = per_person[(per_person["repo"] == "org/sdk") & (per_person["period"] == "30d")]
    assert scoped["total_actions"].sum() == _row(table, repo="org/sdk", period="30d")["total_actions"]


def test_merges_are_credited_to_the_merger(events):
    """A merge counts for whoever merged, not the pull request's author."""
    table = contributor_activity(events, WINDOWS)
    assert _row(table, contributor="bob", period="all")["merges_done"] == 1
    assert _row(table, contributor="alice", period="all")["merges_done"] == 0


def test_contributor_work_mix_and_repositories_per_window(events):
    """Work mix, shares, repositories touched and the active span follow the window."""
    table = contributor_activity(events, WINDOWS)

    alice_all = _row(table, contributor="alice", period="all")
    assert alice_all["repos_touched"] == 2
    assert (alice_all["building_and_fixing"], alice_all["organizing_and_answering"]) == (2, 1)
    assert (alice_all["building_share"], alice_all["organizing_share"], alice_all["reviewing_share"]) == (67, 33, 0)

    alice_week = _row(table, contributor="alice", period="7d")
    assert (alice_week["repos_touched"], alice_week["total_actions"], alice_week["building_share"]) == (1, 1, 100)

    bob = _row(table, contributor="bob", period="7d")
    assert (bob["reviewing_and_guiding"], bob["reviewing_share"]) == (2, 100)

    # The first and last tracked action span the window's own events.
    assert alice_all["first_active"] == NOW - timedelta(days=100)
    assert alice_all["last_active"] == NOW - timedelta(days=2)
    assert "dependabot[bot]" not in set(table["contributor"])


def test_pairs_break_a_contributor_down_by_repository(events):
    """The pair table splits one person's actions by repository."""
    table = repo_contributor_activity(events, WINDOWS)
    alice_docs = _row(table, repo="org/docs", contributor="alice", period="all")
    assert (alice_docs["prs_opened"], alice_docs["total_actions"], alice_docs["building_share"]) == (1, 1, 100)
    assert table[(table["contributor"] == "alice") & (table["period"] == "7d")]["repo"].tolist() == ["org/sdk"]
    carol_sdk = _row(table, repo="org/sdk", contributor="carol", period="all")
    assert (carol_sdk["labels_applied"], carol_sdk["organizing_share"]) == (1, 100)


def test_monthly_activity_by_repository_and_contributor(events):
    """Monthly counts per repository and per contributor, by type."""
    by_repo = monthly_activity(events, "repo")
    sdk = by_repo[by_repo["repo"] == "org/sdk"].set_index("month")
    assert list(sdk.index) == ["2026-06"]
    assert sdk.loc[
        "2026-06", ["prs_opened", "reviews_given", "merges_done", "issues_opened", "labels_applied"]
    ].tolist() == [
        1,
        1,
        1,
        1,
        1,
    ]
    by_person = monthly_activity(events, "contributor")
    assert by_person[by_person["contributor"] == "alice"]["month"].tolist() == ["2026-03", "2026-06"]


def test_no_events_give_empty_tables_with_their_columns():
    """No events still yield every table, empty but with its columns."""
    empty = combined_activity_events([], [])
    for table in (
        repo_activity(empty, WINDOWS),
        contributor_activity(empty, WINDOWS),
        repo_contributor_activity(empty, WINDOWS),
        monthly_activity(empty, "repo"),
    ):
        assert table.empty
        assert len(table.columns) > 3
