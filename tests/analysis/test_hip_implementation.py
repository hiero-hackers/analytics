"""Tests for the HIP-implementation analysis transforms."""

from __future__ import annotations

from datetime import UTC, datetime

from hiero_analytics.analysis.hip_implementation import (
    RECENT_COHORT,
    build_adoption_funnel,
    build_evidence_tables,
    build_hip_summary,
    build_process_checks,
    build_repo_activity,
    build_repo_engagement,
    status_bucket,
)
from hiero_analytics.data_sources.models import HipReferenceRecord, HipSpecRecord


def _spec(number: int, status: str = "Final", title: str | None = None) -> HipSpecRecord:
    return HipSpecRecord(
        number=number,
        title=title or f"Spec {number}",
        status=status,
        category="Service",
        hip_type="Standards Track",
        created="2025-01-01",
        updated="",
        updated_at=datetime(2024, 1, 1, tzinfo=UTC),
    )


def _ref(
    repo: str,
    pr_number: int,
    hip: int | None,
    state: str = "MERGED",
    merged_at: datetime | None = datetime(2026, 1, 15, tzinfo=UTC),
    qualifier: str = "",
) -> HipReferenceRecord:
    return HipReferenceRecord(
        repo=repo,
        pr_number=pr_number,
        pr_title=f"PR {pr_number}",
        pr_state=state,
        pr_created_at=datetime(2026, 1, 1, tzinfo=UTC),
        pr_merged_at=merged_at if state == "MERGED" else None,
        hip=hip,
        match_sources=("body" if qualifier else "title") if hip is not None else "",
        snippet=f"HIP-{hip}" if hip is not None else "",
        qualifier=qualifier,
        author="alice",
        updated_at=datetime(2026, 1, 16, tzinfo=UTC),
    )


INVENTORY = [_spec(551), _spec(904, status="Approved"), _spec(173, status="Accepted"), _spec(60, status="Withdrawn")]

REFERENCES = [
    # sdk-java: two merged PRs for 551, one merged for 904, one marker.
    _ref("org/sdk-java", 1, 551),
    _ref("org/sdk-java", 2, 551),
    _ref("org/sdk-java", 3, 904),
    _ref("org/sdk-java", 4, None),
    # sdk-go: one open-only reference to 904, plus markers.
    _ref("org/sdk-go", 10, 904, state="OPEN"),
    _ref("org/sdk-go", 11, None),
    # docs repo: swept but never mentions a HIP.
    _ref("org/docs", 20, None),
    # a mention of a number missing from the inventory → unknown, not counted.
    _ref("org/sdk-java", 5, 9999),
    # a qualified body-only mention: kept as evidence, excluded from counts.
    _ref("org/sdk-go", 12, 551, qualifier="waiting on"),
]


def test_status_bucket_mapping():
    """Lifecycle statuses map onto the four reporting buckets."""
    assert status_bucket("Final") == "final_active"
    assert status_bucket("active") == "final_active"
    assert status_bucket("Approved") == "approved_accepted"
    assert status_bucket("Last Call") == "in_review"
    assert status_bucket("Withdrawn") == "retired"
    assert status_bucket("Something New") == "retired"


def test_evidence_split_validates_against_inventory():
    """Mentions split into inventory-validated evidence and unknown numbers."""
    evidence, unknown = build_evidence_tables(REFERENCES, INVENTORY)
    assert set(evidence["hip"]) == {551, 904}
    assert len(evidence) == 5  # markers excluded, unknown excluded, qualified kept
    assert list(unknown["hip"]) == [9999]
    qualified = evidence[evidence["qualifier"] != ""]
    assert list(qualified["pr_number"]) == [12]
    assert not qualified["counted"].any()
    row = evidence[evidence["pr_number"] == 1].iloc[0]
    assert row["hip_title"] == "Spec 551"
    assert row["url"] == "https://github.com/org/sdk-java/pull/1"


def test_repo_activity_counts_merged_and_open_separately():
    """Matrix cells count merged and open referencing PRs separately."""
    evidence, _ = build_evidence_tables(REFERENCES, INVENTORY)
    activity = build_repo_activity(evidence)
    cell_551 = activity[(activity["hip"] == 551) & (activity["repo"] == "org/sdk-java")].iloc[0]
    assert cell_551["merged_prs"] == 2 and cell_551["open_prs"] == 0
    cell_904_go = activity[(activity["hip"] == 904) & (activity["repo"] == "org/sdk-go")].iloc[0]
    assert cell_904_go["merged_prs"] == 0 and cell_904_go["open_prs"] == 1


def test_repo_engagement_includes_zero_reference_repos():
    """Engagement keeps zero-reference repos with their swept denominator."""
    evidence, _ = build_evidence_tables(REFERENCES, INVENTORY)
    engagement = build_repo_engagement(REFERENCES, evidence)
    by_repo = engagement.set_index("repo")
    assert by_repo.loc["org/sdk-java", "distinct_hips_merged"] == 2
    assert by_repo.loc["org/sdk-java", "total_prs"] == 5  # 4 distinct PRs + unknown-ref PR
    # The docs repo never mentions a HIP but still appears with its denominator.
    assert by_repo.loc["org/docs", "distinct_hips_merged"] == 0
    assert by_repo.loc["org/docs", "total_prs"] == 1
    # Open-only references don't count toward merged breadth.
    assert by_repo.loc["org/sdk-go", "distinct_hips_merged"] == 0
    # The qualified PR is swept (denominator) but adds no engaged breadth.
    assert by_repo.loc["org/sdk-go", "total_prs"] == 3


def test_qualified_references_do_not_reach_counts():
    """A distancing-cue reference never moves matrix, summary, or engagement."""
    refs = [_ref("org/sdk-go", 12, 551, qualifier="waiting on")]
    evidence, _ = build_evidence_tables(refs, INVENTORY)
    assert build_repo_activity(evidence).empty
    summary = build_hip_summary(INVENTORY, evidence).set_index("hip")
    assert summary.loc[551, "evidence_class"] == "none"


def test_hip_summary_evidence_classes():
    """The ledger classifies each spec by its strongest evidence."""
    evidence, _ = build_evidence_tables(REFERENCES, INVENTORY)
    summary = build_hip_summary(INVENTORY, evidence).set_index("hip")
    assert summary.loc[551, "evidence_class"] == "merged"
    assert summary.loc[551, "repos_with_merged"] == 1
    assert summary.loc[904, "evidence_class"] == "merged"  # merged in java, open in go
    assert summary.loc[904, "open_prs"] == 1
    assert summary.loc[173, "evidence_class"] == "none"
    assert summary.loc[173, "status_bucket"] == "approved_accepted"
    assert summary.loc[60, "status_bucket"] == "retired"


def test_open_only_hip_classifies_as_open_only():
    """Open-only references classify as open_only, not merged."""
    refs = [_ref("org/sdk-go", 10, 904, state="OPEN")]
    evidence, _ = build_evidence_tables(refs, INVENTORY)
    summary = build_hip_summary(INVENTORY, evidence).set_index("hip")
    assert summary.loc[904, "evidence_class"] == "open_only"


def test_empty_inputs_produce_empty_tables():
    """Empty inputs yield empty (but well-formed) tables."""
    evidence, unknown = build_evidence_tables([], INVENTORY)
    assert evidence.empty and unknown.empty
    assert build_repo_activity(evidence).empty
    summary = build_hip_summary(INVENTORY, evidence)
    assert (summary["evidence_class"] == "none").all()


def test_evidence_sorted_newest_hip_first():
    """Evidence and unknown tables lead with the highest HIP numbers."""
    evidence, _unknown = build_evidence_tables(REFERENCES, INVENTORY)
    assert list(evidence["hip"]) == sorted(evidence["hip"], reverse=True)


def test_process_checks_flag_final_specs_only():
    """Final specs missing a release or citations are flagged; approved ones are not."""
    inventory = [_spec(551), _spec(600), _spec(173, status="Accepted")]
    refs = [_ref("org/sdk-java", 1, 551)]
    evidence, _ = build_evidence_tables(refs, inventory)
    checks = build_process_checks(build_hip_summary(inventory, evidence))
    flagged = checks.groupby("check")["hip"].apply(list).to_dict()
    # Both Final specs lack a release in their frontmatter.
    assert flagged["final_missing_release"] == [551, 600]
    # Only the uncited Final spec is a citation gap; the Accepted one is not.
    assert flagged["final_no_citing_prs"] == [600]


def test_adoption_funnel_counts_and_cohorts():
    """The funnel counts each mechanical stage, all-time and for the recent cohort."""
    inventory = [
        _spec(551),  # Final, merged evidence in 2 repos (created 2024 per _spec)
        _spec(173, status="Accepted"),  # approved, no evidence
        _spec(60, status="Withdrawn"),  # never approved
    ]
    refs = [_ref(f"org/repo-{n}", n, 551) for n in range(1, 6)]  # five repos → broad
    evidence, _ = build_evidence_tables(refs, inventory)
    funnel = build_adoption_funnel(build_hip_summary(inventory, evidence))
    all_time = funnel[funnel["cohort"] == "all specs"].set_index("stage")["hips"]
    assert all_time["proposed"] == 3
    assert all_time.iloc[1] == 2  # reached approval: 551 + 173
    assert all_time.iloc[2] == 1  # merged evidence: 551
    assert all_time.iloc[3] == 1  # broad: 551 has merged PRs in 5 repos
    assert set(funnel["cohort"]) == {"all specs", RECENT_COHORT}


def test_pre_hiero_era_references_are_flagged_not_counted():
    """A PR merged before the Hiero era stays in evidence, flagged and uncounted."""
    refs = [
        _ref("org/sdk-java", 1, 551),  # 2026 → in era
        _ref("org/sdk-java", 2, 551, merged_at=datetime(2024, 1, 10, tzinfo=UTC)),
    ]
    evidence, _ = build_evidence_tables(refs, INVENTORY)
    by_pr = evidence.set_index("pr_number")
    assert bool(by_pr.loc[1, "counted"]) is True
    assert by_pr.loc[2, "qualifier"] == "pre-Hiero era"
    assert bool(by_pr.loc[2, "counted"]) is False
