"""Run event-based difficulty-over-time analytics for an organization."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from hiero_analytics.analysis.timeseries import (
    DIFFICULTY_OVER_TIME_COLUMN_ORDER,
    get_difficulty_over_time_event_based,
)
from hiero_analytics.config.charts import DIFFICULTY_COLORS
from hiero_analytics.config.paths import ORG, ensure_org_dirs
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import (
    fetch_org_issue_label_events_graphql,
    fetch_org_issues_graphql,
)
from hiero_analytics.domain.labels import (
    DIFFICULTY_ADVANCED,
    DIFFICULTY_BEGINNER,
    DIFFICULTY_GOOD_FIRST_ISSUE,
    DIFFICULTY_INTERMEDIATE,
)
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.plotting.lines import plot_stacked_area

WINDOW_DAYS = 365
TIMELINE_MAX_WORKERS = 3
DIFFICULTY_OVER_TIME_LABELS = [
    DIFFICULTY_GOOD_FIRST_ISSUE.name,
    DIFFICULTY_BEGINNER.name,
    DIFFICULTY_INTERMEDIATE.name,
    DIFFICULTY_ADVANCED.name,
]




def main() -> None:
    """Generate an org-wide event-based difficulty-over-time chart."""
    org_data_dir, org_charts_dir = ensure_org_dirs(ORG)
    end_at = datetime.now(UTC)
    start_at = end_at - timedelta(days=WINDOW_DAYS)

    print(f"Running event-based difficulty-over-time analytics for org: {ORG}")
    print(
        "Window: "
        f"{start_at.date().isoformat()} to {end_at.date().isoformat()}"
    )

    client = GitHubClient()
    
    # Fetch all issues (open and closed) to get the complete issue set.
    all_issues = fetch_org_issues_graphql(client, org=ORG, states=["OPEN", "CLOSED"])
    print(f"Fetched {len(all_issues)} total issues")

    # Fetch label add/remove events (GraphQL timelineItems) to identify label
    # application dates. Only LABELED/UNLABELED events are transferred, so this
    # avoids the repo-wide REST event firehose and its 300-page truncation.
    timeline_events = fetch_org_issue_label_events_graphql(
        client,
        org=ORG,
        states=["OPEN", "CLOSED"],
        max_workers=TIMELINE_MAX_WORKERS,
    )
    print(f"Fetched {len(timeline_events)} repository issue events")

    # Build event-based difficulty-over-time series.
    difficulty_over_time = pd.DataFrame(
        get_difficulty_over_time_event_based(
            all_issues,
            timeline_events,
            start_at=start_at,
            today=end_at,
        )
    )
    if difficulty_over_time.empty:
        print("No difficulty-over-time data available")
        return

    difficulty_over_time = difficulty_over_time[["date", *DIFFICULTY_OVER_TIME_COLUMN_ORDER]]

    save_dataframe(
        difficulty_over_time,
        org_data_dir / "difficulty_over_time_event_based_weekly.csv",
    )

    plot_stacked_area(
        difficulty_over_time,
        x_col="date",
        stack_cols=DIFFICULTY_OVER_TIME_COLUMN_ORDER,
        labels=DIFFICULTY_OVER_TIME_LABELS,
        title="Open Issues by Difficulty Over Time (Event-Based)",
        output_path=org_charts_dir / "difficulty_over_time_event_based_weekly.png",
        colors=DIFFICULTY_COLORS,
        xlabel="Date",
        ylabel="Open issues",
    )

    print("Event-based difficulty-over-time analytics complete")


if __name__ == "__main__":
    main()
