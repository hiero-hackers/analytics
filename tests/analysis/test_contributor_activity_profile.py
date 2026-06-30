"""Tests for the per-contributor activity-family profile builder."""

from __future__ import annotations

from datetime import UTC, datetime

from hiero_analytics.analysis.contributor_activity_profile import (
    ACTIVITY_FAMILY,
    build_account_activity_by_repo,
    build_contributor_profiles,
    build_contributor_profiles_by_repo,
    contributor_activity_to_dataframe,
)
from hiero_analytics.data_sources.models import (
    ContributorActivityRecord,
    IssueTimelineEventRecord,
)


def _label(actor: str | None, issue: int, *, repo: str = "hiero-ledger/sdk", month: int = 1):
    return IssueTimelineEventRecord(
        repo=repo,
        issue_number=issue,
        event_type="labeled",
        occurred_at=datetime(2024, month, 1, tzinfo=UTC),
        label="good first issue",
        actor=actor,
    )


def _event(
    *,
    actor: str,
    activity_type: str,
    repo: str = "hiero-ledger/sdk",
    target_number: int = 1,
    target_author: str | None = None,
    detail: str | None = None,
    month: int = 1,
) -> ContributorActivityRecord:
    target_type = "issue" if activity_type == "authored_issue" else "pull_request"
    return ContributorActivityRecord(
        repo=repo,
        activity_type=activity_type,
        actor=actor,
        occurred_at=datetime(2024, month, 1, tzinfo=UTC),
        target_type=target_type,
        target_number=target_number,
        target_author=target_author if target_author is not None else actor,
        detail=detail,
    )


def test_family_mapping_covers_known_activity_types():
    """Each known activity type maps to exactly one family."""
    assert ACTIVITY_FAMILY["authored_pull_request"] == "building_and_fixing"
    assert ACTIVITY_FAMILY["reviewed_pull_request"] == "reviewing_and_guiding"
    assert ACTIVITY_FAMILY["merged_pull_request"] == "reviewing_and_guiding"
    assert ACTIVITY_FAMILY["authored_issue"] == "organizing_and_answering"


def test_empty_records_return_empty_profile_with_schema():
    """No records yields an empty frame that still carries the profile columns."""
    df = build_contributor_profiles([])
    assert df.empty
    assert "building_share" in df.columns
    assert "reviews_for_newcomers" in df.columns


def test_event_frame_tags_family_and_month():
    """The raw event frame tags each row with its family and a YYYY-MM month."""
    df = contributor_activity_to_dataframe([_event(actor="a", activity_type="reviewed_pull_request", month=3)])
    row = df.iloc[0]
    assert row["family"] == "reviewing_and_guiding"
    assert row["month"] == "2024-03"


def test_profile_counts_and_family_shares():
    """Counts roll up per contributor and shares sum across the three families."""
    records = [
        # asha: opens 2 PRs, reviews 3 (all others'), merges 1 -> review-heavy
        _event(actor="asha", activity_type="authored_pull_request", target_number=1),
        _event(actor="asha", activity_type="authored_pull_request", target_number=2),
        _event(
            actor="asha",
            activity_type="reviewed_pull_request",
            target_number=10,
            target_author="lee",
            detail="APPROVED",
        ),
        _event(
            actor="asha",
            activity_type="reviewed_pull_request",
            target_number=11,
            target_author="sam",
            detail="CHANGES_REQUESTED",
        ),
        _event(
            actor="asha",
            activity_type="reviewed_pull_request",
            target_number=12,
            target_author="lee",
            detail="COMMENTED",
            month=2,
        ),
        _event(actor="asha", activity_type="merged_pull_request", target_number=10, target_author="lee"),
        _event(actor="asha", activity_type="authored_issue", target_number=20),
    ]

    profiles = build_contributor_profiles(records)
    asha = profiles[profiles["contributor"] == "asha"].iloc[0]

    assert asha["prs_opened"] == 2
    assert asha["reviews_given"] == 3
    assert asha["merges_done"] == 1
    assert asha["issues_opened"] == 1
    assert asha["building_and_fixing"] == 2  # 2 authored PRs
    assert asha["reviewing_and_guiding"] == 4  # 3 reviews + 1 merge
    assert asha["organizing_and_answering"] == 1  # 1 issue opened
    # shares are integer percentages of the 7-event family total
    assert asha["building_share"] + asha["reviewing_share"] + asha["organizing_share"] == 100
    assert asha["changes_requested"] == 1  # one CHANGES_REQUESTED review
    assert asha["reviews_of_others"] == 3  # none of the reviews were self
    assert asha["months_active"] == 2  # months 1 and 2


def test_reviews_for_newcomers_uses_pr_count_heuristic():
    """A review counts 'for a newcomer' when the PR author has <= newcomer_max_prs PRs."""
    records = [
        # sam is a newcomer: only 1 authored PR in the window
        _event(actor="sam", activity_type="authored_pull_request", target_number=1),
        # lee is established: 3 authored PRs
        _event(actor="lee", activity_type="authored_pull_request", target_number=2),
        _event(actor="lee", activity_type="authored_pull_request", target_number=3),
        _event(actor="lee", activity_type="authored_pull_request", target_number=4),
        # asha reviews one of each
        _event(actor="asha", activity_type="reviewed_pull_request", target_number=1, target_author="sam"),
        _event(actor="asha", activity_type="reviewed_pull_request", target_number=2, target_author="lee"),
    ]

    profiles = build_contributor_profiles(records, newcomer_max_prs=2)
    asha = profiles[profiles["contributor"] == "asha"].iloc[0]

    assert asha["reviews_given"] == 2
    assert asha["reviews_for_newcomers"] == 1  # sam (1 PR) counts, lee (3 PRs) does not


def test_profiles_sorted_by_last_active_desc():
    """Output is ordered most-recently-active first (recency, not volume)."""
    records = [
        # 'early' did MORE (2 PRs) but longer ago; 'recent' did less but later.
        _event(actor="early", activity_type="authored_pull_request", target_number=1, month=1),
        _event(actor="early", activity_type="authored_pull_request", target_number=2, month=2),
        _event(actor="recent", activity_type="authored_pull_request", target_number=3, month=6),
    ]
    profiles = build_contributor_profiles(records)
    assert list(profiles["contributor"]) == ["recent", "early"]  # by recency, not count


def test_first_and_last_active_span_the_contributors_events():
    """first_active / last_active are the earliest and latest event timestamps."""
    records = [
        _event(actor="a", activity_type="authored_pull_request", target_number=1, month=1),
        _event(actor="a", activity_type="reviewed_pull_request", target_number=2,
               target_author="b", month=5),
    ]
    a = build_contributor_profiles(records).iloc[0]
    assert a["first_active"] == datetime(2024, 1, 1, tzinfo=UTC)
    assert a["last_active"] == datetime(2024, 5, 1, tzinfo=UTC)


def test_label_events_fold_into_organizing_family():
    """Labels applied (with an actor) count toward the organizing family."""
    records = [_event(actor="asha", activity_type="authored_pull_request", target_number=1)]
    labels = [_label("asha", 5), _label("asha", 6)]

    profiles = build_contributor_profiles(records, labels)
    asha = profiles[profiles["contributor"] == "asha"].iloc[0]

    assert asha["labels_applied"] == 2
    assert asha["organizing_and_answering"] == 2  # 0 issues opened + 2 labels applied
    assert asha["building_and_fixing"] == 1
    assert asha["building_share"] + asha["reviewing_share"] + asha["organizing_share"] == 100


def test_label_events_without_actor_are_ignored():
    """Older label events with no actor don't inflate anyone's organizing count."""
    records = [_event(actor="asha", activity_type="authored_pull_request", target_number=1)]
    labels = [_label(None, 5)]

    profiles = build_contributor_profiles(records, labels)
    asha = profiles[profiles["contributor"] == "asha"].iloc[0]

    assert asha["labels_applied"] == 0


def test_label_only_contributor_still_appears():
    """Someone who only triages (labels) shows up with a full organizing share."""
    profiles = build_contributor_profiles([], [_label("triager", 5), _label("triager", 6)])
    triager = profiles[profiles["contributor"] == "triager"].iloc[0]

    assert triager["labels_applied"] == 2
    assert triager["organizing_share"] == 100


def test_bots_are_excluded_from_profiles():
    """Automation accounts are dropped from both activity and label events."""
    records = [
        _event(actor="asha", activity_type="authored_pull_request", target_number=1),
        _event(actor="dependabot", activity_type="authored_pull_request", target_number=2),
        _event(actor="coderabbitai", activity_type="reviewed_pull_request", target_number=3),
        _event(actor="github-actions", activity_type="authored_pull_request", target_number=4),
    ]
    labels = [_label("renovate[bot]", 5), _label("maria", 6)]

    profiles = build_contributor_profiles(records, labels)

    assert set(profiles["contributor"]) == {"asha", "maria"}  # bots gone, humans kept


def test_profiles_by_repo_scope_each_persons_work_to_that_repo():
    """The same person can show a different shape per repo."""
    records = [
        # asha builds in repo x, reviews in repo y
        _event(actor="asha", activity_type="authored_pull_request", repo="o/x", target_number=1),
        _event(actor="asha", activity_type="reviewed_pull_request", repo="o/y", target_number=2, target_author="b"),
        _event(actor="b", activity_type="authored_pull_request", repo="o/y", target_number=2),
    ]

    by_repo = build_contributor_profiles_by_repo(records)

    assert set(by_repo) == {"o/x", "o/y"}
    asha_x = by_repo["o/x"].set_index("contributor").loc["asha"]
    asha_y = by_repo["o/y"].set_index("contributor").loc["asha"]
    assert asha_x["building_and_fixing"] == 1 and asha_x["reviewing_and_guiding"] == 0
    assert asha_y["reviewing_and_guiding"] == 1 and asha_y["building_and_fixing"] == 0
    # repos_touched is 1 within each repo-scoped table
    assert asha_x["repos_touched"] == 1


def test_profiles_by_repo_empty_input():
    """No events yields an empty mapping."""
    assert build_contributor_profiles_by_repo([]) == {}


def test_account_activity_by_repo_filters_and_labels_repos():
    """For each account, one row per repo it works in, case-insensitive match."""
    records = [
        _event(actor="Maria", activity_type="authored_pull_request", repo="o/x", target_number=1),
        _event(actor="Maria", activity_type="reviewed_pull_request", repo="o/y", target_number=2, target_author="b"),
        _event(actor="bob", activity_type="authored_pull_request", repo="o/x", target_number=3),
    ]
    by_repo = build_contributor_profiles_by_repo(records)

    table = build_account_activity_by_repo({"maria"}, by_repo)  # lower-case input

    assert set(table["account"]) == {"Maria"}  # bob excluded
    assert set(table["repo"]) == {"o/x", "o/y"}  # both repos Maria works in
    assert list(table.columns[:2]) == ["repo", "account"]


def test_account_activity_by_repo_empty_when_no_match():
    """Unknown accounts yield an empty, schema-carrying table."""
    by_repo = build_contributor_profiles_by_repo(
        [_event(actor="a", activity_type="authored_pull_request", target_number=1)]
    )
    table = build_account_activity_by_repo({"nobody"}, by_repo)
    assert table.empty
    assert list(table.columns[:2]) == ["repo", "account"]
