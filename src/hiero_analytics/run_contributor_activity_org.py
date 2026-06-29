"""Export contributor activity reports for a GitHub organization."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.colors import Normalize

from hiero_analytics.config.paths import ORG, ensure_org_dirs
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import fetch_org_contributor_activity_graphql
from hiero_analytics.data_sources.governance_config import (
    ROLE_PRIORITY,
    build_repo_role_lookup,
    fetch_governance_config,
)
from hiero_analytics.export.save import save_dataframe

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

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
        if not actor or action is None:
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


def _build_activity_summary_dataframe(records, repo_role_lookup: dict[str, dict[str, str]]) -> pd.DataFrame:
    """Aggregate contributor activity into the role overview table."""
    rollup = _build_activity_rollup(records, repo_role_lookup)

    columns = ["contributor name", "role", *ACTION_TYPES, "activity score"]
    rows: list[dict[str, object]] = []
    for item in rollup.values():
        rows.append(
            {
                "contributor name": item["contributor name"],
                "role": ROLE_LABELS.get(str(item["role key"]), "General User"),
                "issues": bool(item["issues"]),
                "reviews": bool(item["reviews"]),
                "prs created": bool(item["prs created"]),
                "prs merged": bool(item["prs merged"]),
                "activity score": int(item["weighted activity score"]),
            }
        )

    if not rows:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(rows)
    return df.sort_values(by=["activity score", "contributor name"], ascending=[False, True]).reset_index(drop=True)


def _build_top_active_contributors_dataframe(summary_df: pd.DataFrame) -> pd.DataFrame:
    """Filter the overview to high-engagement contributors without elevated roles."""
    columns = ["rank", *summary_df.columns.tolist()]
    if summary_df.empty:
        return pd.DataFrame(columns=columns)

    top_active = summary_df[
        (summary_df["role"] == "General User")
        & (summary_df["activity score"] > 0)
    ].copy()

    if top_active.empty:
        return pd.DataFrame(columns=columns)

    top_active = top_active.sort_values(
        by=["activity score", "prs created", "reviews", "issues", "prs merged", "contributor name"],
        ascending=[False, False, False, False, False, True],
    ).reset_index(drop=True)
    top_active.insert(0, "rank", range(1, len(top_active) + 1))
    return top_active


def _build_activity_heatmap_dataframe(
    records,
    repo_role_lookup: dict[str, dict[str, str]],
    *,
    months_back: int = HEATMAP_MONTHS,
) -> pd.DataFrame:
    """Build a contributor-by-month activity matrix for the heatmap."""
    month_columns = _recent_month_keys(months_back)
    rollup = _build_activity_rollup(records, repo_role_lookup)

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

    month_columns = [column for column in heatmap_df.columns if column not in {"contributor name", "role", "activity score"}]
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


def main() -> None:
    """Fetch contributor activity records and export the report tables."""
    org_data_dir, org_charts_dir = ensure_org_dirs(ORG)

    print(f"Running contributor activity export for org: {ORG}")

    gov_config = fetch_governance_config()
    repo_role_lookup = build_repo_role_lookup(gov_config)

    client = GitHubClient()
    logger.info("Fetching contributor activity for org: %s", ORG)

    records = fetch_org_contributor_activity_graphql(
        client,
        org=ORG,
        lookback_days=183,
    )

    logger.info("Fetched %d contributor activity records", len(records))
    print(f"Fetched {len(records)} contributor activity events")

    if records:
        sample = records[0]
        logger.info(
            "Sample record: repo=%s, actor=%s, activity_type=%s",
            sample.repo,
            sample.actor,
            sample.activity_type,
        )

    summary_df = _build_activity_summary_dataframe(records, repo_role_lookup)
    top_active_df = _build_top_active_contributors_dataframe(summary_df)
    heatmap_df = _build_activity_heatmap_dataframe(records, repo_role_lookup)

    overview_path = org_data_dir / "contributor_activity_role_overview.csv"
    top_active_path = org_data_dir / "contributor_activity_top_active.csv"
    heatmap_data_path = org_data_dir / "contributor_activity_heatmap.csv"
    heatmap_chart_path = org_charts_dir / "contributor_activity_heatmap.png"

    save_dataframe(summary_df, overview_path)
    save_dataframe(top_active_df, top_active_path)
    save_dataframe(heatmap_df, heatmap_data_path)
    _save_activity_heatmap_chart(heatmap_df, heatmap_chart_path)

    print(f"Saved role overview to: {overview_path}")
    print(f"Saved top active contributors to: {top_active_path}")
    print(f"Saved heatmap data to: {heatmap_data_path}")
    print(f"Saved heatmap chart to: {heatmap_chart_path}")


if __name__ == "__main__":
    main()