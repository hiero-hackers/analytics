"""Render the analytics CSVs and charts into a single self-contained ``dashboard.html``.

A no-server local frontend organized as macro (dashboard family) → org → section.
It auto-discovers each org's data under ``outputs/data/org/<org>/`` (rendered as
tables) and charts under ``outputs/charts/org/<org>/`` (embedded as base64 images),
and renders only the sections that have a CSV or PNG — so an org with no governance
config simply shows the contributor tables, and a chart macro/tab appears only when
its images exist. Run after the data pipelines (last step in ``run_all``).
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import pandas as pd

from hiero_analytics.config.logging_config import setup_logging
from hiero_analytics.config.paths import ORG, ORG_CHARTS_DIR, ORG_DATA_DIR, OUTPUTS_DIR, ensure_output_dirs
from hiero_analytics.export.dashboard import build_dashboard_html

logger = logging.getLogger(__name__)

# The dashboard is organized as macro (family) → org → section. Today there is a
# single macro built from SECTION_SPECS below; a future dashboard family (e.g.
# onboarding, scorecards) becomes a new macro: build its ``org_tabs`` the same way
# and append ``{"name": ..., "org_tabs": [...]}`` to ``macros`` in main(). The macro
# tab bar appears automatically once there is more than one.
MACRO_NAME = "Contributors & governance"

# Chart families. Each macro lists, per org, image sections built from PNGs under
# outputs/charts/org/<org>/. The first macro's name matches MACRO_NAME, so its
# charts are appended to that macro's existing data tables; the rest become new
# chart-only macro tabs. Missing files are skipped, so a section/macro/tab only
# appears when its charts exist. Org-level charts only (per-repo charts excluded).
CHART_MACROS = [
    {
        "name": MACRO_NAME,
        "charts": {
            "hiero-ledger": [
                {
                    "id": "maintainer-pipeline",
                    "title": "Maintainer pipeline",
                    "description": "How the maintainer/committer pipeline has moved over time and across repos.",
                    "files": [
                        ("By year", "maintainer_pipeline_yearly.png"),
                        ("By repo", "maintainer_pipeline_by_repo.png"),
                    ],
                },
                {
                    "id": "role-networks",
                    "title": "Activity networks by role",
                    "slideshow": True,
                    "description": (
                        "Repositories linked by the people they share, one slide per group "
                        "(maintainers, committers, triage, general contributors, and all contributors). "
                        "Each bubble is a repo sized by that group's active members; links mean shared "
                        "members (thicker = more). Colour = repository type. Use Prev/Next; click to enlarge."
                    ),
                    "files": [
                        ("Maintainers", "maintainer_network.png"),
                        ("Committers", "committer_network.png"),
                        ("Triage", "triage_network.png"),
                        ("General contributors", "general_network.png"),
                        ("All contributors", "all_network.png"),
                    ],
                },
            ],
            "hiero-hackers": [
                {
                    "id": "org-overview",
                    "title": "Organization overview (org-wide)",
                    "description": (
                        "Org-wide view of hiero-hackers: repositories ranked by contributor count, "
                        "the language mix across repos, and how many repos pushed in the last 30 days."
                    ),
                    "files": [
                        ("Top repositories by contributors", "contributor_counts.png"),
                        ("Programming languages", "language_distribution.png"),
                        ("Repository push activity (30d)", "push_activity.png"),
                    ],
                },
                {
                    "id": "contributor-network",
                    "title": "Contributor network",
                    "description": (
                        "Each bubble is a repository, sized by its active contributors; two repos are "
                        "linked when they share contributors. Colour = repository type. Click to enlarge."
                    ),
                    "files": [("Repositories linked by shared contributors", "all_network.png")],
                },
            ],
        },
    },
    {
        "name": "Issues & onboarding",
        "charts": {
            "hiero-ledger": [
                {
                    "id": "good-first-issues",
                    "title": "Good first issues",
                    "description": "Good-first-issue (and good-first-issue-candidate) pipeline and history.",
                    "files": [
                        ("GFI pipeline", "gfi_pipeline.png"),
                        ("GFI state by year", "gfi_yearly_state_line.png"),
                        ("GFI + GFIC by repo", "total_gfi_gfic_by_repo.png"),
                    ],
                },
                {
                    "id": "issue-difficulty",
                    "title": "Issue difficulty",
                    "description": "Difficulty mix of open issues and how it has shifted over time.",
                    "files": [
                        ("By repo (30d)", "difficulty_by_repo_30_days.png"),
                        ("Distribution incl. unknown (30d)", "difficulty_distribution_with_unknown_30_days.png"),
                        ("Distribution excl. unknown (30d)", "difficulty_distribution_without_unknown_30_days.png"),
                        ("Over time (weekly)", "difficulty_over_time_event_based_weekly.png"),
                    ],
                },
            ],
        },
    },
    {
        "name": "Security & scorecards",
        "charts": {
            "hiero-ledger": [
                {
                    "id": "scorecard",
                    "title": "OpenSSF scorecard",
                    "description": "Org-level OpenSSF scorecard and its per-check breakdown.",
                    "files": [
                        ("Org scorecard", "org_scorecard.png"),
                        ("Score breakdown", "org_scorecard_breakdown.png"),
                    ],
                },
                {
                    "id": "ownership",
                    "title": "Code owners & CI runners",
                    "description": "CODEOWNERS coverage and the CI runners configured across repos.",
                    "files": [
                        ("Code-owner coverage", "org_codeowner_summary.png"),
                        ("Runners", "org_runner_chart.png"),
                    ],
                },
            ],
        },
    },
    {
        "name": "Community",
        "charts": {
            "hiero-ledger": [
                {
                    "id": "discord",
                    "title": "Discord activity",
                    "description": "Discord channel categories, monthly traffic, and recent activity.",
                    "files": [
                        ("Channel categories", "hiero_discord_channel_categories.png"),
                        ("Monthly traffic", "hiero_discord_monthly_traffic.png"),
                        ("Recent activity (30d)", "hiero_discord_recent_activity_30d.png"),
                    ],
                },
            ],
        },
    },
]

# Each section: which CSV it reads and how to render it. Sections appear only when
# their CSV exists and is non-empty, so governance-only tables (role coverage,
# teams) are simply absent for orgs without a governance config.
SECTION_SPECS = [
    {
        "id": "profiles",
        "file": "contributor_activity_profiles.csv",
        "title": "All contributors",
        "description": "Every contributor's org-wide activity (all-time), most recently active first.",
        "columns": [
            ("contributor", "contributor"),
            ("prs_opened", "PRs"),
            ("reviews_given", "reviews"),
            ("merges_done", "merges"),
            ("issues_opened", "issues"),
            ("labels_applied", "labels"),
            ("repos_touched", "repos"),
            ("last_active", "last active"),
        ],
    },
    {
        "id": "repoactivity",
        "file": "repo_activity_overview.csv",
        "title": "Repository activity — permission-holders by role",
        "description": (
            "One row per repo: how many maintainers, committers and triage hold it, how many "
            "are active in the last 90 days, and recent activity split by role. Sorted by recent "
            "activity (most active first). 'actions' = PRs + reviews + merges + issues + labels, "
            "summed; '90d' columns are the last 90 days, 'all-time' is cumulative."
        ),
        "columns": [
            ("repo", "repo"),
            ("maintainers", "maintainers"),
            ("committers", "committers"),
            ("triage", "triage"),
            ("active_recent", "active 90d"),
            ("maintainer_actions_recent", "maint. actions 90d"),
            ("committer_actions_recent", "comm. actions 90d"),
            ("triage_actions_recent", "triage actions 90d"),
            ("actions_recent", "actions 90d"),
            ("actions_all_time", "actions all-time"),
            ("last_active", "last active"),
        ],
    },
    {
        "id": "understaffed",
        "file": "maintainer_coverage_risk.csv",
        "title": "Repos with one or fewer active maintainers",
        "description": (
            "Repos where at most one maintainer has been active in the last 90 days. 'maintainers' is "
            "the total on paper; 'committers' and 'triage' show others with access to the repo. Fewest "
            "active maintainers first."
        ),
        "columns": [
            ("repo", "repo"),
            ("maintainers", "maintainers"),
            ("active_maintainers", "active maintainers"),
            ("committers", "committers"),
            ("triage", "triage"),
        ],
    },
    {
        "id": "loadshare",
        "file": "review_load_share.csv",
        "title": "Who carries the review load",
        "description": (
            "For each repo, the share of review+merge work (last 90 days) done by the single busiest "
            "person who can merge — committer or maintainer. 'mergers' is how many reviewed/merged; "
            "'top role' is whether the busiest is a committer or maintainer; 'top %' is their share, "
            "'top-2 %' the top two combined. Highest concentration first; repos with under 20 recent "
            "review+merge actions are omitted."
        ),
        "columns": [
            ("repo", "repo"),
            ("mergers", "mergers"),
            ("load_recent", "review+merge 90d"),
            ("top_carrier", "top carrier"),
            ("top_role", "top role"),
            ("top_pct", "top %"),
            ("top2_pct", "top-2 %"),
        ],
    },
    {
        "id": "account",
        "file": "maintainer_activity_by_repo.csv",
        "title": "Maintainer activity by repo (all-time)",
        "description": "Type a name to see which repos a maintainer works in and the role they hold there.",
        "columns": [
            ("account", "account"),
            ("repo", "repo"),
            ("repo_role", "role here"),
            ("prs_opened", "PRs"),
            ("reviews_given", "reviews"),
            ("merges_done", "merges"),
            ("issues_opened", "issues"),
            ("labels_applied", "labels"),
            ("last_active", "last active"),
        ],
    },
    {
        "id": "repo",
        "file": "role_coverage_all.csv",
        "title": "Roles and recent activity by repo",
        "description": (
            "Type a repo to see its permission-holders and their contributions in this repo "
            "— both all-time and over the last 90 days (the '90d' columns) — plus whether "
            "each has recent activity here. Status counts a holder 'active' with any activity "
            "in the last 90 days."
        ),
        "columns": [
            ("repo", "repo"),
            ("user", "user"),
            ("granted_role", "role"),
            ("status", "status"),
            ("days_since_active", "days since active"),
            ("prs_opened", "PRs"),
            ("reviews_given", "reviews"),
            ("merges_done", "merges"),
            ("issues_opened", "issues"),
            ("labels_applied", "labels"),
            ("prs_recent", "PRs 90d"),
            ("reviews_recent", "reviews 90d"),
            ("merges_recent", "merges 90d"),
            ("issues_recent", "issues 90d"),
            ("labels_recent", "labels 90d"),
        ],
    },
    {
        "id": "gonedark",
        "file": "role_coverage_globally_quiet.csv",
        "title": "Permission-holders with no recent activity (180+ days)",
        "description": (
            "Permission-holders with no recorded activity in any repo in the last 180 days. "
            "Useful for keeping access lists current. A blank 'days since active' means no "
            "recorded activity yet."
        ),
        "columns": [
            ("user", "user"),
            ("highest_role", "highest role"),
            ("roles", "roles held"),
            ("repos_held", "repos"),
            ("days_since_active", "days since active"),
            ("last_active", "last active"),
        ],
    },
    {
        "id": "tscrepo",
        "file": "tsc_activity_by_repo.csv",
        "title": "TSC activity by repo (all-time)",
        "description": "For TSC members with activity, which repos they work in and the role they hold there.",
        "columns": [
            ("account", "member"),
            ("repo", "repo"),
            ("repo_role", "role here"),
            ("prs_opened", "PRs"),
            ("reviews_given", "reviews"),
            ("merges_done", "merges"),
            ("issues_opened", "issues"),
            ("labels_applied", "labels"),
            ("last_active", "last active"),
        ],
    },
    {
        "id": "teams",
        "file": "team_activity_summary.csv",
        "title": "Team activity overview",
        "description": (
            "Each governance team's size, how many members have recent activity, and the "
            "team's recent-activity status (180-day window). Teams with no recent activity "
            "are listed first."
        ),
        "columns": [
            ("team", "team"),
            ("members", "members"),
            ("active_members", "active"),
            ("status", "status"),
            ("days_since_active", "days since active"),
            ("prs_opened", "PRs"),
            ("reviews_given", "reviews"),
            ("merges_done", "merges"),
            ("issues_opened", "issues"),
            ("labels_applied", "labels"),
        ],
    },
    {
        "id": "teamrepo",
        "file": "team_activity_by_repo.csv",
        "title": "Team activity by repo (all-time)",
        "description": "Which repos each team is active in — type a team or repo to filter.",
        "columns": [
            ("team", "team"),
            ("repo", "repo"),
            ("members_active", "members active"),
            ("prs_opened", "PRs"),
            ("reviews_given", "reviews"),
            ("merges_done", "merges"),
            ("issues_opened", "issues"),
            ("labels_applied", "labels"),
            ("last_active", "last active"),
        ],
    },
]


# Display order for the tables: high-level aggregates first (repos, then teams),
# drilling down to per-holder cohorts, ending at the most granular individual list
# (every contributor). Decoupled from SECTION_SPECS definition order on purpose.
_SECTION_ORDER = [
    "repoactivity",  # per-repo rollup (most aggregate)
    "understaffed",  # repos with <=1 active maintainer
    "loadshare",  # review-load concentration
    "teams",  # per-team rollup
    "teamrepo",  # team × repo
    "repo",  # role-holders per repo
    "account",  # maintainers, by repo
    "tscrepo",  # TSC members, by repo
    "gonedark",  # individual holders who've gone quiet
    "profiles",  # every contributor (most granular)
]


def _load(path: Path) -> pd.DataFrame:
    """Read a CSV, or an empty frame if it doesn't exist."""
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


# Counted at each person's highest role across all repos, so the three buckets
# partition the permission-holders (no double-counting someone who is, say,
# maintainer in one repo and triage in another).
_ROLE_RANK = {"triage": 1, "committer": 2, "maintainer": 3}


def _holders_by_highest_role(coverage: pd.DataFrame) -> dict[str, int]:
    """Distinct permission-holders per highest role, from ``role_coverage_all``."""
    if coverage.empty or "granted_role" not in coverage or "user" not in coverage:
        return {}
    df = coverage.assign(
        _u=coverage["user"].str.lower(),
        _r=coverage["granted_role"].map(_ROLE_RANK).fillna(0),
    )
    highest = df.sort_values("_r").groupby("_u")["granted_role"].last()
    counts = highest.value_counts()
    return {role: int(counts.get(role, 0)) for role in _ROLE_RANK}


def _img_data_uri(path: Path) -> str | None:
    """Base64 ``data:`` URI for a PNG, or None if missing (keeps the file self-contained)."""
    if not path.exists():
        return None
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _chart_sections(org: str, chart_specs: list[dict]) -> list[dict]:
    """Build image-gallery sections for an org from its chart specs (missing files skipped)."""
    chart_dir = ORG_CHARTS_DIR / org
    sections = []
    for spec in chart_specs:
        charts = [
            {"title": caption, "src": src}
            for caption, filename in spec["files"]
            if (src := _img_data_uri(chart_dir / filename)) is not None
        ]
        if charts:
            section = {
                "id": spec["id"], "title": spec["title"], "description": spec["description"], "charts": charts,
            }
            if spec.get("slideshow"):
                section["slideshow"] = True
            sections.append(section)
    return sections


def _org_tab(org_name: str, org_data_dir: Path) -> dict | None:
    """Build one org's tab from whatever CSVs it has, or None if it has no data."""
    loaded = {spec["id"]: _load(org_data_dir / spec["file"]) for spec in SECTION_SPECS}
    if loaded["profiles"].empty:
        return None  # no core contributor data for this org

    # High-level → individual order (see _SECTION_ORDER), non-empty tables only.
    specs_by_id = {spec["id"]: spec for spec in SECTION_SPECS}
    sections = [
        {
            "id": spec["id"],
            "title": spec["title"],
            "description": spec["description"],
            "columns": spec["columns"],
            "rows": loaded[spec["id"]].to_dict("records"),
        }
        for section_id in _SECTION_ORDER
        if (spec := specs_by_id[section_id]) and not loaded[section_id].empty
    ]

    metrics = [("contributors", len(loaded["profiles"]))]
    role_counts = _holders_by_highest_role(loaded["repo"])
    for role, label in (("maintainer", "maintainers"), ("committer", "committers"), ("triage", "triage")):
        if role in role_counts:
            metrics.append((label, role_counts[role]))
    if not loaded["gonedark"].empty:
        metrics.append(("quiet permission-holders (180d+)", len(loaded["gonedark"])))
    if "status" in loaded["teams"]:
        metrics.append(("quiet teams", int((loaded["teams"]["status"] == "quiet").sum())))

    return {"org": org_name, "metrics": metrics, "sections": sections}


def _ordered_orgs() -> list[str]:
    """All orgs that have data or charts, the configured ORG first then alphabetical."""
    names: set[str] = set()
    for base in (ORG_DATA_DIR, ORG_CHARTS_DIR):
        if base.exists():
            names |= {p.name for p in base.iterdir() if p.is_dir()}
    return sorted(names, key=lambda n: (n != ORG, n))


def main() -> None:
    """Build the local macro→org→section HTML dashboard from CSV tables and chart PNGs."""
    ensure_output_dirs()
    ORG_DATA_DIR.mkdir(parents=True, exist_ok=True)

    orgs = _ordered_orgs()
    table_tabs = {org: tab for org in orgs if (tab := _org_tab(org, ORG_DATA_DIR / org)) is not None}

    macros = []
    for macro in CHART_MACROS:
        is_tables_macro = macro["name"] == MACRO_NAME
        org_tabs = []
        for org in orgs:
            table_sections: list[dict] = []
            metrics: list = []
            if is_tables_macro and org in table_tabs:
                table_sections = list(table_tabs[org]["sections"])
                metrics = table_tabs[org]["metrics"]
            # Charts first, then tables (high-level → individual within the tables).
            sections = _chart_sections(org, macro["charts"].get(org, [])) + table_sections
            if sections:
                org_tabs.append({"org": org, "metrics": metrics, "sections": sections})
        if org_tabs:
            macros.append({"name": macro["name"], "org_tabs": org_tabs})

    if not macros:
        logger.warning("No org data or charts found; dashboard not written")
        return

    output = OUTPUTS_DIR / "dashboard.html"
    output.write_text(build_dashboard_html(macros), encoding="utf-8")
    logger.info(
        "Wrote %s — %d macro(s): %s", output, len(macros), ", ".join(m["name"] for m in macros)
    )


if __name__ == "__main__":
    setup_logging()
    main()
