"""Render the contributor-activity heatmap for an organization.

A weighted-activity view: the most active contributors (top rows) by month over
the recent window, coloured by intensity. This is the ranked, score-based view —
it complements ``run_contributor_activity_org`` (the descriptive, non-ranking
profile tables and co-membership networks), which never scores or ranks.

It reuses the persisted org-wide contributor-activity dataset (populated earlier
in ``run_all``), so it issues no extra GitHub fetch when that dataset exists.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.colors import Normalize

from hiero_analytics.config.logging_config import setup_logging
from hiero_analytics.config.paths import ORG, dataset_path, ensure_org_dirs
from hiero_analytics.data_sources.dataset_store import load_dataset
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import fetch_org_contributor_activity_graphql
from hiero_analytics.data_sources.governance_config import (
    ROLE_PRIORITY,
    build_repo_role_lookup,
    fetch_governance_config,
)
from hiero_analytics.data_sources.models import ContributorActivityRecord
from hiero_analytics.export.save import save_dataframe

logger = logging.getLogger(__name__)

ROLE_LABELS = {
    "general_user": "General User",
    "triage": "Triage",
    "committer": "Committer",
    "maintainer": "Maintainer",
}

ACTION_TYPES = ["issues", "reviews", "prs created", "prs merged"]

ACTIVITY_TYPE_TO_ACTION = {
    "authored_issue": "issues",
    "reviewed_pull_request": "reviews",
    "authored_pull_request": "prs created",
    "merged_pull_request": "prs merged",
}

ACTIVITY_WEIGHTS = {
    "issues": 2,
    "reviews": 3,
    "prs created": 3,
    "prs merged": 2,
}

HEATMAP_MONTHS = 6
HEATMAP_TOP_ROWS = 25

# Secondary composition org rendered alongside the primary org. It has no
# governance config, so its contributors carry no role label — the heatmap colours
# by activity rather than role, so the chart itself is unaffected.
HACKERS_ORG = "hiero-hackers"

# Automation accounts excluded from the heatmap — they aren't people. Matched
# case-insensitively, and any GitHub App login (the "[bot]" suffix) is excluded
# too, so new bots are dropped without needing to be listed here.
BOT_LOGINS = frozenset(
    {
        "dependabot",
        "dependabot-preview",
        "coderabbit",
        "coderabbitai",
        "github-actions",
        "renovate",
        "renovate-bot",
        "swirlds-automation",
        "hedera-github-bot",
        "hedera-local-node-bot",
    }
)


def _as_utc(value: datetime) -> datetime:
    """Normalize datetimes to UTC for monthly grouping."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _month_key(value: datetime) -> str:
    """Return a stable month bucket label for a timestamp."""
    return _as_utc(value).strftime("%Y-%m")


def _recent_month_keys(months_back: int) -> list[str]:
    """Return the most recent month labels, oldest first."""
    current_month = pd.Period(pd.Timestamp.now(tz="UTC"), freq="M")
    return [str(period) for period in pd.period_range(end=current_month, periods=months_back, freq="M")]


def _activity_action(activity_type: str) -> str | None:
    """Map a normalized activity event to a report bucket."""
    return ACTIVITY_TYPE_TO_ACTION.get(activity_type)


def _is_bot(login: str) -> bool:
    """True when a login is an automation account rather than a person."""
    name = login.strip().lower()
    return name.endswith("[bot]") or name in BOT_LOGINS


def _build_activity_rollup(
    records,
    repo_role_lookup: dict[str, dict[str, str]],
) -> dict[str, dict[str, object]]:
    """Aggregate contributor actions into a per-person rollup."""
    per_contributor: dict[str, dict[str, object]] = defaultdict(
        lambda: {
            "contributor name": "",
            "role key": "general_user",
            "role priority": ROLE_PRIORITY["general_user"],
            "issues": 0,
            "reviews": 0,
            "prs created": 0,
            "prs merged": 0,
            "weighted activity score": 0,
            "monthly scores": defaultdict(int),
        }
    )

    for record in records:
        actor = (record.actor or "").strip()
        action = _activity_action(record.activity_type)
        if not actor or action is None or record.occurred_at is None or _is_bot(actor):
            continue

        actor_key = actor.lower()
        repo_name = record.repo.split("/")[-1]
        detected_role = repo_role_lookup.get(repo_name, {}).get(actor_key, "general_user")

        row = per_contributor[actor_key]
        row["contributor name"] = actor

        current_role = str(row["role key"])
        if ROLE_PRIORITY[detected_role] > ROLE_PRIORITY[current_role]:
            row["role key"] = detected_role
            row["role priority"] = ROLE_PRIORITY[detected_role]

        row[action] = int(row[action]) + 1
        row["weighted activity score"] = int(row["weighted activity score"]) + ACTIVITY_WEIGHTS[action]
        row["monthly scores"][_month_key(record.occurred_at)] += ACTIVITY_WEIGHTS[action]

    return per_contributor


def _build_activity_heatmap_dataframe(
    records,
    repo_role_lookup: dict[str, dict[str, str]],
    *,
    months_back: int = HEATMAP_MONTHS,
) -> pd.DataFrame:
    """Build a contributor-by-month activity matrix for the heatmap.

    Only activity within the displayed window (the most recent ``months_back``
    months) is scored, so the "activity score", the top-N selection and the month
    columns all agree — the busiest *recent* contributors rise to the top, not
    people who were active long ago but are quiet now.
    """
    month_columns = _recent_month_keys(months_back)
    window = set(month_columns)
    windowed = [
        record
        for record in records
        if record.occurred_at is not None and _month_key(record.occurred_at) in window
    ]
    rollup = _build_activity_rollup(windowed, repo_role_lookup)

    rows: list[dict[str, object]] = []
    for item in rollup.values():
        monthly_scores = item["monthly scores"]
        row = {
            "contributor name": item["contributor name"],
            "role": ROLE_LABELS.get(str(item["role key"]), "General User"),
            "activity score": int(item["weighted activity score"]),
        }
        for month in month_columns:
            row[month] = int(monthly_scores.get(month, 0))
        rows.append(row)

    columns = ["contributor name", "role", "activity score", *month_columns]
    if not rows:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(rows)
    return df.sort_values(by=["activity score", "contributor name"], ascending=[False, True]).reset_index(drop=True)


def _save_activity_heatmap_chart(heatmap_df: pd.DataFrame, output_path: Path) -> None:
    """Render a color-coded activity heatmap to a PNG file."""
    if heatmap_df.empty:
        return

    month_columns = [
        column for column in heatmap_df.columns if column not in {"contributor name", "role", "activity score"}
    ]
    chart_df = heatmap_df.head(HEATMAP_TOP_ROWS).copy()
    if chart_df.empty:
        return

    values = chart_df[month_columns].to_numpy(dtype=float)
    max_value = float(values.max()) if values.size else 0.0
    normalization = Normalize(vmin=0, vmax=max(max_value, 1.0))
    cmap = plt.get_cmap("RdYlGn")

    width = max(10.0, len(month_columns) * 1.15 + 4.0)
    height = max(6.0, len(chart_df) * 0.4 + 2.4)
    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_facecolor("#F6F8FB")
    ax.set_facecolor("#FFFFFF")
    ax.grid(False)  # the project style enables a grid globally; it must not overlay the heatmap

    image = ax.imshow(values, aspect="auto", cmap=cmap, norm=normalization, interpolation="nearest")

    ax.set_xticks(range(len(month_columns)))
    ax.set_xticklabels(month_columns, rotation=45, ha="right")
    ax.set_yticks(range(len(chart_df)))
    ax.set_yticklabels(chart_df["contributor name"].tolist())

    for row_index, row_values in enumerate(values):
        for column_index, cell_value in enumerate(row_values):
            text_color = "#0F172A" if normalization(cell_value) < 0.6 else "#FFFFFF"
            ax.text(
                column_index,
                row_index,
                int(cell_value),
                ha="center",
                va="center",
                fontsize=9,
                fontweight="semibold",
                color=text_color,
            )

    ax.set_title(
        f"Top {len(chart_df)} Contributor Activity Heatmap",
        loc="left",
        color="#0F172A",
    )
    ax.set_xlabel("Month")
    ax.set_ylabel("Contributor")
    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.tick_params(axis="both", colors="#64748B")
    colorbar = fig.colorbar(image, ax=ax, pad=0.02)
    colorbar.set_label("Weighted monthly activity score")

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def _load_or_fetch_records(client: GitHubClient, org: str) -> list[ContributorActivityRecord]:
    """Reuse the persisted org-wide contributor-activity dataset, or fetch it.

    The same ``all`` dataset is populated by the maintainer/profile pipelines
    earlier in ``run_all``, so this reads it from disk instead of issuing another
    org-wide fetch. With no dataset yet (first run) it falls back to fetching.
    """
    state = load_dataset(dataset_path("contributor_activity", org, "all"), ContributorActivityRecord)
    if state is not None:
        records, _ = state
        logger.info("Reusing persisted %s contributor_activity dataset (%d records)", org, len(records))
        return records
    logger.info("No persisted %s contributor_activity dataset; fetching from GitHub", org)
    return fetch_org_contributor_activity_graphql(client, org=org, lookback_days=None)


def _build_heatmap_for_org(
    org: str,
    repo_role_lookup: dict[str, dict[str, str]],
    client: GitHubClient,
) -> None:
    """Build the heatmap (data table + chart) for one org from its activity dataset."""
    org_data_dir, org_charts_dir = ensure_org_dirs(org)
    records = _load_or_fetch_records(client, org)
    logger.info("Using %d activity records for the %s heatmap", len(records), org)

    heatmap_df = _build_activity_heatmap_dataframe(records, repo_role_lookup)
    save_dataframe(heatmap_df, org_data_dir / "contributor_activity_heatmap.csv")
    _save_activity_heatmap_chart(heatmap_df, org_charts_dir / "contributor_activity_heatmap.png")
    logger.info("Contributor activity heatmap complete for %s (%d contributors)", org, len(heatmap_df))


def main() -> None:
    """Build the contributor-activity heatmap for the primary org and hiero-hackers."""
    client = GitHubClient()

    # Primary org: contributors are labelled by their governance role.
    _build_heatmap_for_org(ORG, build_repo_role_lookup(fetch_governance_config()), client)

    # Secondary composition org: no governance config, so no role labels. Isolated
    # so a problem here can't drop the primary org's heatmap.
    if HACKERS_ORG != ORG:
        try:
            _build_heatmap_for_org(HACKERS_ORG, {}, client)
        except Exception:
            logger.exception("Heatmap for %s failed; the primary org heatmap is unaffected", HACKERS_ORG)


if __name__ == "__main__":
    setup_logging()
    main()
