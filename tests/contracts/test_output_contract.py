"""End-to-end output contract: pipelines must produce what the dashboard spec lists.

Runs the entire default pipeline run (plus the extra-org contributor pass and the
dashboard) against synthetic fetch results, into a temporary outputs tree, then
asserts the producer↔spec contract in both directions:

- every CSV a table section lists (including derived period variants) exists;
- every chart PNG a macro lists exists (except charts owned by CLI-only
  pipelines, which the default run legitimately does not execute);
- every org-level CSV/PNG actually produced is either listed by the spec or
  explicitly accounted for below.

Without this, a renamed pipeline output fails *silently*: the dashboard skips
missing PNGs, renders blank cells for renamed CSV columns, and drops metric
tiles — all with zero test failures. Here the drift fails loudly instead.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import matplotlib
import pytest

matplotlib.use("Agg")

import hiero_analytics.config.paths as paths
import hiero_analytics.pipelines.affiliation as affiliation_mod
import hiero_analytics.pipelines.codeowner_and_runner as codeowner_mod
import hiero_analytics.pipelines.contributor_activity as activity_mod
import hiero_analytics.pipelines.contributor_heatmap as heatmap_mod
import hiero_analytics.pipelines.contributor_profiles as profiles_mod
import hiero_analytics.pipelines.dashboard as dashboard_mod
import hiero_analytics.pipelines.difficulty as difficulty_mod
import hiero_analytics.pipelines.difficulty_over_time as difficulty_time_mod
import hiero_analytics.pipelines.hiero_hackers as hackers_mod
import hiero_analytics.pipelines.maintainer_pipeline as maintainer_mod
import hiero_analytics.pipelines.onboarding as onboarding_mod
import hiero_analytics.pipelines.role_coverage as role_coverage_mod
import hiero_analytics.pipelines.run_all as run_all
import hiero_analytics.pipelines.scorecard as scorecard_mod
from hiero_analytics.dashboard_spec import CHART_MACROS, TABLE_FAMILIES
from hiero_analytics.data_sources.models import (
    CodeOwnersRecord,
    ContributorActivityRecord,
    IssueRecord,
    IssueTimelineEventRecord,
    PullRequestDifficultyRecord,
    RepositoryRecord,
    RunnerRecord,
    ScorecardRecord,
)
from hiero_analytics.domain.periods import ACTIVITY_PERIODS

# Every table section across the table-bearing macros (Contributors, Governance).
ALL_SECTION_SPECS = [spec for family in TABLE_FAMILIES.values() for spec in family.SECTION_SPECS]

PRIMARY = "hiero-ledger"
HACKERS = "hiero-hackers"
_NOW = datetime.now(UTC)

# Charts listed by the spec but owned by CLI-only pipelines: the default run
# legitimately does not produce them, so existence is not asserted here.
CLI_ONLY_CHARTS = {
    "hiero_discord_channel_categories.png",
    "hiero_discord_monthly_traffic.png",
    "hiero_discord_recent_activity_30d.png",
}

# Org-level artifacts pipelines produce that the dashboard spec deliberately
# does not list: chart-companion data tables (the PNG is the dashboard-facing
# artifact; the CSV is its exportable source) and non-dashboard reports.
CHART_COMPANION_CSVS = {
    "affiliation_distribution.csv",
    "affiliation_distribution_active.csv",
    "maintainer_affiliations_active.csv",
    "repo_affiliation_composition.csv",
    "repo_affiliation_composition_active.csv",
    "team_affiliation_composition.csv",
    "team_affiliation_composition_active.csv",
    "repo_affiliation_diversity.csv",  # base for spec section; keep for safety
    "contributor_activity_heatmap.csv",
    "org_activity_heatmap.csv",
    "team_activity_heatmap.csv",
    "repo_activity_heatmap.csv",
    "difficulty_distribution_30_days.csv",
    "difficulty_by_repo_30_days.csv",
    "difficulty_over_time_event_based_weekly.csv",
    "maintainer_activity_events.csv",
    "gfi_completers.csv",  # Contributors-tab KPI tile source (completed-a-GFI %)
    "maintainer_pipeline_yearly.csv",
    "maintainer_pipeline_monthly.csv",
    "maintainer_pipeline_weekly.csv",
    "maintainer_pipeline_by_repo.csv",
    "org_runner_status.csv",
    "repo_wise_codeowner_status.csv",
    "language_distribution.csv",
    "push_activity.csv",
    "contributor_counts.csv",
}


# ---------------------------------------------------------------------------
# Synthetic fetch results (one coherent scenario shared by every pipeline)
# ---------------------------------------------------------------------------


def _activity(repo: str, actor: str, activity_type: str, days_ago: int, number: int, target_author: str | None = None):
    return ContributorActivityRecord(
        repo=repo,
        activity_type=activity_type,
        actor=actor,
        occurred_at=_NOW - timedelta(days=days_ago),
        target_type="pull_request" if "pull" in activity_type else "issue",
        target_number=number,
        target_author=target_author or actor,
    )


def _label_event(repo: str, number: int, label: str, days_ago: int, actor: str = "alice", event: str = "labeled"):
    return IssueTimelineEventRecord(
        repo=repo,
        issue_number=number,
        event_type=event,
        occurred_at=_NOW - timedelta(days=days_ago),
        label=label,
        actor=actor,
    )


def _issue(repo: str, number: int, labels: list[str], days_ago: int, state: str = "OPEN"):
    return IssueRecord(
        repo=repo,
        number=number,
        title=f"Issue {number}",
        state=state,
        created_at=_NOW - timedelta(days=days_ago),
        closed_at=None,
        labels=labels,
    )


def _pr(repo: str, number: int, author: str, labels: list[str], merged_days_ago: int):
    merged = _NOW - timedelta(days=merged_days_ago)
    return PullRequestDifficultyRecord(
        repo=repo,
        pr_number=number,
        pr_created_at=merged - timedelta(days=3),
        pr_merged_at=merged,
        pr_additions=10,
        pr_deletions=2,
        pr_changed_files=2,
        issue_number=number * 10,
        issue_labels=labels,
        author=author,
    )


def _repo(org: str, name: str, language: str | None = "Python"):
    return RepositoryRecord(
        full_name=f"{org}/{name}",
        name=name,
        owner=org,
        pushed_at=_NOW - timedelta(days=3),
        language=language,
    )


def _org_activity(org: str) -> list[ContributorActivityRecord]:
    """Activity spanning two repos and several actors, recent and stale."""
    repo_a, repo_b = f"{org}/sdk-python", f"{org}/sdk-java"
    records = []
    number = 1
    for days_ago in (2, 5, 10, 40, 200):
        for actor, target in (
            ("alice", "bob"),
            ("bob", "alice"),
            ("carol", "alice"),
            ("dave", "erin"),
            ("erin", "dave"),
        ):
            records.append(_activity(repo_a, actor, "authored_pull_request", days_ago, number))
            records.append(_activity(repo_a, actor, "reviewed_pull_request", days_ago, number + 1, target))
            records.append(_activity(repo_a, actor, "merged_pull_request", days_ago, number + 2, target))
            records.append(_activity(repo_b, actor, "authored_issue", days_ago, number + 3))
            number += 4
    return records


GOVERNANCE = {
    "teams": [
        {"name": "sdk-python-maintainers", "maintainers": ["alice"], "members": ["bob"]},
        {"name": "sdk-java-maintainers", "maintainers": ["carol"], "members": ["dave"]},
        {"name": "tsc", "maintainers": [], "members": ["alice", "carol"]},
        # Five resolved, recently active members so the team-composition charts
        # (which need >= 4 resolved members) render in both All and Active views.
        {"name": "core", "maintainers": [], "members": ["alice", "bob", "carol", "dave", "erin"]},
        # Write- and triage-permission teams so the committer and triage role
        # networks (Governance tab) have holders to render.
        {"name": "sdk-devs", "maintainers": [], "members": ["bob", "dave"]},
        {"name": "triagers", "maintainers": [], "members": ["erin"]},
    ],
    "repositories": [
        {
            "name": "sdk-python",
            "teams": {"sdk-python-maintainers": "maintain", "sdk-devs": "write", "triagers": "triage"},
        },
        {"name": "sdk-java", "teams": {"sdk-java-maintainers": "maintain", "sdk-devs": "write"}},
    ],
}

AFFILIATIONS = {
    "alice": "Acme Corp",
    "bob": "Acme Corp",
    "carol": "Independent",
    "dave": "Beta LLC",
    "erin": "Acme Corp",
}

ISSUES = [
    _issue(f"{PRIMARY}/sdk-python", 1, ["good first issue"], days_ago=5),
    _issue(f"{PRIMARY}/sdk-python", 2, ["beginner"], days_ago=10),
    _issue(f"{PRIMARY}/sdk-java", 3, ["advanced"], days_ago=15),
    _issue(f"{PRIMARY}/sdk-java", 4, [], days_ago=3),
]

TIMELINE = [
    _label_event(f"{PRIMARY}/sdk-python", 1, "good first issue", days_ago=5),
    _label_event(f"{PRIMARY}/sdk-python", 2, "beginner", days_ago=10),
    _label_event(f"{PRIMARY}/sdk-java", 3, "advanced", days_ago=15),
]

REPO_ISSUES = [_issue(f"{PRIMARY}/hiero-sdk-python", n, ["good first issue"], days_ago=60 - n * 7) for n in range(1, 6)]

REPO_PRS = [
    _pr(f"{PRIMARY}/hiero-sdk-python", n, "alice" if n % 2 else "bob", ["good first issue"], merged_days_ago=50 - n * 7)
    for n in range(1, 6)
]


# ---------------------------------------------------------------------------
# The full run, once per module
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def outputs_root(tmp_path_factory) -> Path:
    """Run every default pipeline + dashboard into a temp outputs tree."""
    root = tmp_path_factory.mktemp("outputs")
    mp = pytest.MonkeyPatch()
    try:
        # Redirect the whole output tree; ensure_* helpers read these at call time.
        mp.setattr(paths, "OUTPUTS_DIR", root)
        mp.setattr(paths, "DATA_DIR", root / "data")
        mp.setattr(paths, "CHARTS_DIR", root / "charts")
        mp.setattr(paths, "ORG_DATA_DIR", root / "data" / "org")
        mp.setattr(paths, "REPO_DATA_DIR", root / "data" / "repo")
        mp.setattr(paths, "ORG_CHARTS_DIR", root / "charts" / "org")
        mp.setattr(paths, "REPO_CHARTS_DIR", root / "charts" / "repo")
        mp.setattr(paths, "DATASETS_DIR", root / "data" / "datasets")
        # dashboard imported the dir constants directly.
        mp.setattr(dashboard_mod, "OUTPUTS_DIR", root)
        mp.setattr(dashboard_mod, "ORG_DATA_DIR", root / "data" / "org")
        mp.setattr(dashboard_mod, "ORG_CHARTS_DIR", root / "charts" / "org")

        # Fetch-layer stubs, per pipeline namespace.
        for mod in (difficulty_mod, difficulty_time_mod):
            mp.setattr(mod, "fetch_org_issues_graphql", lambda _c, **_k: ISSUES)
            mp.setattr(mod, "fetch_org_issue_label_events_graphql", lambda _c, **_k: TIMELINE)
        mp.setattr(onboarding_mod, "fetch_repo_issues_graphql", lambda _c, **_k: REPO_ISSUES)
        mp.setattr(onboarding_mod, "fetch_repo_merged_pr_difficulty_graphql", lambda _c, **_k: REPO_PRS)
        mp.setattr(profiles_mod, "fetch_repo_merged_pr_difficulty_graphql", lambda _c, **_k: REPO_PRS)
        mp.setattr(activity_mod, "fetch_org_merged_pr_difficulty_graphql", lambda _c, _org, **_k: REPO_PRS)
        for mod in (maintainer_mod, heatmap_mod, role_coverage_mod, affiliation_mod):
            mp.setattr(mod, "fetch_governance_config", lambda *_a, **_k: GOVERNANCE)
        for mod in (maintainer_mod, heatmap_mod, role_coverage_mod, affiliation_mod, activity_mod):
            mp.setattr(mod, "load_contributor_activity", lambda _c, org: _org_activity(org))
        for mod in (role_coverage_mod, affiliation_mod, activity_mod):
            mp.setattr(mod, "load_issue_label_events", lambda _c, _org: TIMELINE)
        mp.setattr(affiliation_mod, "load_affiliations", lambda: AFFILIATIONS)
        mp.setattr(affiliation_mod, "load_manual_logins", set)
        mp.setattr(
            scorecard_mod, "fetch_org_repos_graphql", lambda _c, org: [_repo(org, "sdk-python"), _repo(org, "sdk-java")]
        )
        mp.setattr(
            scorecard_mod,
            "fetch_repo_scorecard",
            lambda name: ScorecardRecord(repo=name, score=7.5, checks={"Maintained": 10, "Code-Review": 8}, date=_NOW),
        )
        mp.setattr(
            codeowner_mod,
            "get_codeowners_for_repos",
            lambda _c, _org, repos: [CodeOwnersRecord(repo=r.name, status=i % 2 == 0) for i, r in enumerate(repos)],
        )
        mp.setattr(
            codeowner_mod,
            "get_workflow_for_repos",
            lambda _c, _org, repos: [
                RunnerRecord(
                    repo=r.name,
                    workflow_file="ci.yml",
                    job_name="build",
                    runner="ubuntu-latest",
                    is_self_hosted=i % 2 == 0,
                )
                for i, r in enumerate(repos)
            ],
        )
        mp.setattr(
            hackers_mod,
            "fetch_org_repos_graphql",
            lambda _c, org: [_repo(org, "analytics"), _repo(org, "hips", "Markdown")],
        )
        mp.setattr(hackers_mod, "fetch_org_contributor_activity_graphql", lambda _c, org: _org_activity(org))

        mp.setattr(run_all, "setup_logging", lambda: None)
        mp.setattr(run_all, "EXTRA_ORGS", [HACKERS])
        mp.setattr(heatmap_mod, "EXTRA_ORGS", [HACKERS])

        run_all.main()  # raises SystemExit(1) if any pipeline failed
        yield root
    finally:
        mp.undo()


# ---------------------------------------------------------------------------
# Contract assertions
# ---------------------------------------------------------------------------


def _spec_chart_files() -> dict[str, set[str]]:
    """Org -> set of chart filenames the spec lists."""
    per_org: dict[str, set[str]] = {}
    for macro in CHART_MACROS:
        for org, specs in macro["charts"].items():
            files = per_org.setdefault(org, set())
            for spec in specs:
                for _caption, variants in spec["files"]:
                    files.update(filename for _label, filename in variants)
    return per_org


def test_every_spec_table_csv_is_produced(outputs_root: Path):
    """Each section's CSV (and every derived period variant) exists for the primary org."""
    org_data = outputs_root / "data" / "org" / PRIMARY
    missing = []
    for spec in ALL_SECTION_SPECS:
        expected = [spec["file"]]
        if spec.get("periods"):
            stem = Path(spec["file"]).stem
            expected += [period.filename(stem) for period in ACTIVITY_PERIODS]
        missing += [name for name in expected if not (org_data / name).exists()]
        # Freshness contract: every spec-listed base CSV carries its sidecar.
        if (org_data / spec["file"]).exists() and not (org_data / f"{spec['file']}.meta.json").exists():
            missing.append(f"{spec['file']}.meta.json")
    assert not missing, f"spec lists CSVs no pipeline produced: {sorted(missing)}"


def test_every_spec_chart_png_is_produced(outputs_root: Path):
    """Each macro-listed PNG exists for its org (CLI-only pipelines excepted)."""
    missing = []
    for org, files in _spec_chart_files().items():
        chart_dir = outputs_root / "charts" / "org" / org
        missing += [f"{org}/{name}" for name in files - CLI_ONLY_CHARTS if not (chart_dir / name).exists()]
    assert not missing, f"spec lists charts no pipeline produced: {sorted(missing)}"


def test_no_orphan_org_level_outputs(outputs_root: Path):
    """Everything produced at org level is spec-listed or explicitly accounted for."""
    spec_csvs = set()
    for spec in ALL_SECTION_SPECS:
        spec_csvs.add(spec["file"])
        if spec.get("periods"):
            stem = Path(spec["file"]).stem
            spec_csvs.update(period.filename(stem) for period in ACTIVITY_PERIODS)
    period_suffixes = tuple(f"_{period.key}.csv" for period in ACTIVITY_PERIODS)

    orphans = []
    org_data = outputs_root / "data" / "org" / PRIMARY
    for path in org_data.glob("*.csv"):
        name = path.name
        known = name in spec_csvs or name in CHART_COMPANION_CSVS
        # Period variants of chart-companion tables are companions too.
        if not known and name.endswith(period_suffixes):
            base = name
            for suffix in period_suffixes:
                if name.endswith(suffix):
                    base = name.removesuffix(suffix) + ".csv"
                    break
            known = base in CHART_COMPANION_CSVS
        if not known:
            orphans.append(name)

    spec_charts = _spec_chart_files().get(PRIMARY, set())
    org_charts = outputs_root / "charts" / "org" / PRIMARY
    orphans += [p.name for p in org_charts.glob("*.png") if p.name not in spec_charts]

    assert not orphans, f"outputs the dashboard spec doesn't know about: {sorted(orphans)}"


def test_dashboard_html_is_written(outputs_root: Path):
    """The assembled dashboard exists and carries both table-bearing macro tabs."""
    html = (outputs_root / "dashboard.html").read_text(encoding="utf-8")
    assert ">Contributors<" in html  # the people/activity macro button
    assert ">Governance<" in html  # the authority/risk macro button
    assert len(html) > 10_000
