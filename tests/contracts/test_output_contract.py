"""End-to-end output contract: pipelines must produce what the dashboard spec lists.

Runs the entire default pipeline run (plus the extra-org contributor pass and the
data API emit) against synthetic fetch results, into a temporary outputs tree,
then asserts the producer↔spec contract in both directions:

- every CSV a table section lists (including derived period variants) exists;
- every chart PNG a macro lists exists (except charts owned by CLI-only
  pipelines, which the default run legitimately does not execute);
- every org-level CSV/PNG actually produced is either listed by the spec or
  explicitly accounted for below.

Without this, a renamed pipeline output fails *silently*: the web dashboard
skips missing PNGs, renders blank cells for renamed CSV columns, and drops
metric tiles — all with zero test failures. Here the drift fails loudly instead.
"""

from __future__ import annotations

import json
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
import hiero_analytics.pipelines.difficulty as difficulty_mod
import hiero_analytics.pipelines.difficulty_over_time as difficulty_time_mod
import hiero_analytics.pipelines.hiero_hackers as hackers_mod
import hiero_analytics.pipelines.hip_implementation as hip_mod
import hiero_analytics.pipelines.maintainer_pipeline as maintainer_mod
import hiero_analytics.pipelines.onboarding as onboarding_mod
import hiero_analytics.pipelines.releases as releases_mod
import hiero_analytics.pipelines.repo_growth as repo_growth_mod
import hiero_analytics.pipelines.role_coverage as role_coverage_mod
import hiero_analytics.pipelines.run_all as run_all
import hiero_analytics.pipelines.scorecard as scorecard_mod
from hiero_analytics.dashboard_spec import CHART_MACROS, TABLE_FAMILIES, table_variants
from hiero_analytics.data_sources.models import (
    CodeOwnersRecord,
    ContributorActivityRecord,
    HipReferenceRecord,
    HipSpecRecord,
    IssueRecord,
    IssueTimelineEventRecord,
    PullRequestDifficultyRecord,
    ReleaseRecord,
    RepositoryRecord,
    RunnerRecord,
    ScorecardRecord,
)
from hiero_analytics.domain.periods import ACTIVITY_PERIODS

# Every table section across the table-bearing macros (Contributors, Governance),
# flattened through its role variants: a variant the dashboard renders as a tab
# is still its own produced CSV with its own id, columns and API document, so it
# has to face the same production/coverage/orphan checks a top-level section does.
ALL_SECTION_SPECS = [
    variant for family in TABLE_FAMILIES.values() for spec in family.SECTION_SPECS for variant in table_variants(spec)
]

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
    "affiliation_distribution_committers.csv",
    "repo_affiliation_composition.csv",
    "repo_affiliation_composition_committers.csv",
    "team_affiliation_composition.csv",
    "repo_affiliation_diversity.csv",  # base for spec section; keep for safety
    "contributor_activity_heatmap.csv",
    "org_activity_heatmap.csv",
    "team_activity_heatmap.csv",
    "repo_activity_heatmap.csv",
    # Bases; the shared-period variants (_7d/_30d/_365d) are derived below.
    "difficulty_distribution.csv",
    "difficulty_by_repo.csv",
    "difficulty_over_time_event_based_weekly.csv",
    "difficulty_over_time_all_event_based_weekly.csv",
    "maintainer_activity_events.csv",
    "gfi_completers.csv",  # Contributors-tab KPI tile source (completed-a-GFI %)
    "maintainer_pipeline_yearly.csv",
    "maintainer_pipeline_daily.csv",
    "maintainer_pipeline_monthly.csv",
    "maintainer_pipeline_weekly.csv",
    "maintainer_pipeline_by_repo.csv",
    "maintainer_pipeline_by_repo_365d.csv",
    "maintainer_pipeline_by_repo_30d.csv",
    "maintainer_pipeline_by_repo_7d.csv",
    "org_runner_status.csv",
    "language_distribution.csv",
    "push_activity.csv",
    "contributor_counts.csv",
    "hip_repo_engagement.csv",  # HIPs-tab engagement chart companion (embedded as its CSV download)
    "hip_repo_activity.csv",  # long-format source of the coverage matrix (wide CSV embeds in the page)
    "hip_summary.csv",  # per-HIP ledger data behind the funnel, process checks, and matrix (no table dup)
    "hip_adoption_funnel.csv",  # funnel chart companion (embedded as its CSV download)
    "hip_process_checks.csv",  # HIP-1 conformance findings; data artifact only, no dashboard table
    "repo_growth_timeline.csv",  # Repo-growth timeline chart companion
    "release_timeline.csv",  # Release-timeline chart companion (release_repo_summary.csv has its own table section)
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
        created_at=_NOW - timedelta(days=120),
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
        # networks (Governance tab) have holders to render. frank and grace hold
        # write and nothing higher, so the committer role tab on the
        # organisation-diversity card has a population of its own.
        {"name": "sdk-devs", "maintainers": [], "members": ["bob", "dave", "frank", "grace"]},
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
    "frank": "Acme Corp",
    "grace": "Acme Corp",
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

# One repo with releases (including a prerelease), one deliberately with none —
# the second is what exercises the honest-denominator staleness join.
RELEASES = [
    ReleaseRecord(
        repo=f"{PRIMARY}/sdk-python",
        tag_name="v1.0.0",
        name="v1.0.0",
        published_at=_NOW - timedelta(days=200),
        is_prerelease=False,
    ),
    ReleaseRecord(
        repo=f"{PRIMARY}/sdk-python",
        tag_name="v1.1.0-rc1",
        name="v1.1.0-rc1",
        published_at=_NOW - timedelta(days=10),
        is_prerelease=True,
    ),
    ReleaseRecord(
        # Within the last 7 days so every period-tab variant of the release
        # timeline chart (Week/1 month/1 year/Last 18 months) actually renders.
        repo=f"{PRIMARY}/sdk-python",
        tag_name="v1.1.0",
        name="v1.1.0",
        published_at=_NOW - timedelta(days=2),
        is_prerelease=False,
    ),
]


def _hip_spec(number: int, status: str, created: str) -> HipSpecRecord:
    return HipSpecRecord(
        number=number,
        title=f"Spec {number}",
        status=status,
        category="Service",
        hip_type="Standards Track",
        created=created,
        updated="",
        updated_at=_NOW,
    )


def _hip_ref(repo: str, pr_number: int, hip: int | None, state: str = "MERGED") -> HipReferenceRecord:
    return HipReferenceRecord(
        repo=repo,
        pr_number=pr_number,
        pr_title=f"PR {pr_number}",
        pr_state=state,
        pr_created_at=_NOW,
        pr_merged_at=_NOW if state == "MERGED" else None,
        hip=hip,
        match_sources="title" if hip is not None else "",
        snippet=f"HIP-{hip}" if hip is not None else "",
        author="alice",
        updated_at=_NOW,
    )


# Recent spec with merged PRs in two SDKs (drives the coverage matrix + both
# charts), an accepted spec with no activity (drives the attention list), and
# an unknown-number mention (drives the review table).
HIP_SPECS = [
    _hip_spec(551, "Final", f"{_NOW.year}-01-01"),
    _hip_spec(904, "Approved", f"{_NOW.year}-01-01"),
    _hip_spec(173, "Accepted", "2021-10-18"),
]

HIP_REFS = [
    _hip_ref(f"{PRIMARY}/hiero-sdk-python", 1, 551),
    _hip_ref(f"{PRIMARY}/hiero-sdk-java", 2, 551),
    _hip_ref(f"{PRIMARY}/hiero-sdk-java", 3, 904, state="OPEN"),
    _hip_ref(f"{PRIMARY}/hiero-sdk-python", 4, None),
    _hip_ref(f"{PRIMARY}/hiero-sdk-python", 5, 9999),
]


# ---------------------------------------------------------------------------
# The full run, once per module
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def outputs_root(tmp_path_factory) -> Path:
    """Run every default pipeline + the data API emit into a temp outputs tree."""
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
        for mod in (role_coverage_mod, activity_mod):
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
        mp.setattr(
            repo_growth_mod,
            "fetch_org_repos_graphql",
            lambda _c, org: [_repo(org, "sdk-python"), _repo(org, "sdk-java")],
        )
        mp.setattr(
            releases_mod,
            "fetch_org_repos_graphql",
            lambda _c, org: [_repo(org, "sdk-python"), _repo(org, "sdk-java")],
        )
        mp.setattr(releases_mod, "fetch_org_releases_graphql", lambda _c, _org: RELEASES)
        mp.setattr(hackers_mod, "fetch_org_contributor_activity_graphql", lambda _c, org: _org_activity(org))
        mp.setattr(hip_mod, "fetch_hip_inventory", lambda _c, **_k: HIP_SPECS)
        mp.setattr(hip_mod, "fetch_org_pr_hip_refs_graphql", lambda _c, _org, **_k: HIP_REFS)

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
    """Org -> set of chart filenames the spec lists.

    "*" cards are org-independent and best-effort per org, but the primary org
    runs every pipeline, so they are pinned against it.
    """
    per_org: dict[str, set[str]] = {}
    for macro in CHART_MACROS:
        for org, specs in macro["charts"].items():
            files = per_org.setdefault(PRIMARY if org == "*" else org, set())
            for spec in specs:
                for _caption, variants in spec["files"]:
                    files.update(filename for _label, filename in variants)
    return per_org


def test_data_api_covers_every_produced_spec_section(outputs_root: Path):
    """The JSON API lists a document for each spec section whose CSV exists.

    Column validation happened during the run itself (the emitter raises on a
    missing spec-declared column and run_all would have failed); this asserts
    the coverage side: nothing produced+spec-listed is missing from the API.
    """
    api_dir = outputs_root / "data" / "api" / "v1"
    manifest = json.loads((api_dir / "manifest.json").read_text())
    org_data = outputs_root / "data" / "org" / PRIMARY

    listed = {section["id"] for section in manifest["orgs"][PRIMARY]["sections"]}
    for spec in ALL_SECTION_SPECS:
        if (org_data / spec["file"]).exists():
            assert spec["id"] in listed, f"{spec['id']} produced but absent from the data API"
            document = json.loads((api_dir / PRIMARY / f"{spec['id']}.json").read_text())
            declared = {column[0] for column in spec["columns"]}
            emitted = {column["key"] for column in document["columns"]}
            assert declared == emitted
            # The column list agreeing is not enough: the rows are what a
            # consumer actually reads, so an undeclared key leaking into the
            # payload has to fail here too.
            if document["rows"]:
                assert set(document["rows"][0]) == declared
            for period_rows in document.get("periods", {}).values():
                if period_rows:
                    assert set(period_rows[0]) == declared


def test_data_api_emits_the_hip_views(outputs_root: Path):
    """The HIP board and coverage matrix ship as view documents for the org.

    These are the bespoke views the frontend renders as components; if the
    pipeline produced HIP data but the API listed no views, the HIPs tab would
    silently lose its centrepieces.
    """
    api_dir = outputs_root / "data" / "api" / "v1"
    manifest = json.loads((api_dir / "manifest.json").read_text())

    views = manifest["orgs"][PRIMARY]["views"]
    assert [(view["id"], view["kind"]) for view in views] == [("hip-board", "board"), ("hip-matrix", "matrix")]
    for view in views:
        document = json.loads((api_dir / view["path"]).read_text())
        assert document["macro"] == "HIPs"
    matrix = json.loads((api_dir / PRIMARY / "hip-matrix.json").read_text())
    assert matrix["rows"], "matrix emitted with no rows"
    assert matrix["bands"], "matrix emitted with no header bands"


def test_data_api_ships_every_declared_chart_csv(outputs_root: Path):
    """Every chart-declared companion CSV is copied into the API tree.

    The Pages deploy publishes only the API tree and the PNGs, so a download
    the dashboard offers must travel inside the API or 404 in production.
    """
    api_dir = outputs_root / "data" / "api" / "v1"
    manifest = json.loads((api_dir / "manifest.json").read_text())

    missing = []
    for entry in manifest["orgs"].values():
        for section in entry["chart_sections"]:
            download = section.get("download")
            if download and not (api_dir / download["path"]).exists():
                missing.append(download["path"])
    assert not missing, f"chart downloads referenced but not copied: {missing}"
    # The HIP funnel declares a CSV and its pipeline ran, so at least one
    # download must exist end to end.
    hip_charts = [s for s in manifest["orgs"][PRIMARY]["chart_sections"] if s["macro"] == "HIPs"]
    assert any("download" in section for section in hip_charts)


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


def test_every_emitted_kpi_tile_explains_itself(outputs_root: Path):
    """A tile is a lone number, so it must ship its note and derivation steps.

    Charts are guarded by the spec tests; tiles are produced dynamically from
    whatever data exists, so the end-to-end run is where their coverage can
    actually be checked.
    """
    manifest = json.loads((outputs_root / "data" / "api" / "v1" / "manifest.json").read_text())

    unexplained = [
        (org, macro, tile["label"])
        for org, entry in manifest["orgs"].items()
        for macro, tiles in entry["metrics"].items()
        for tile in tiles
        if not tile.get("note") or not tile.get("methodology")
    ]
    assert not unexplained, f"KPI tiles with no explanation: {unexplained}"
