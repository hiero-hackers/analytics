"""Write how long merged pull requests waited for a first review and for a merge.

Reads the persisted org-wide contributor-activity dataset (the same records the
contributor profiles and detail views use) and writes, per org, the waits for
the Week, 1 month and 1 year windows and all time — org-wide and per repository,
split into authors' first PRs and later PRs — plus a monthly trend. Nothing is
fetched beyond that dataset.

Offline-capable: it only reads a dataset another pipeline persisted. See
``analysis/pr_responsiveness`` for the exact definitions and their limits (merged
PRs only, wall-clock hours, bots excluded).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from hiero_analytics.analysis.contributor_activity_profile import combined_activity_events
from hiero_analytics.analysis.pr_responsiveness import (
    monthly_responsiveness,
    pr_response_times,
    responsiveness_summary,
)
from hiero_analytics.config.paths import ORG
from hiero_analytics.domain.periods import ACTIVITY_PERIODS
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.pipelines._shared import load_contributor_activity, org_context

logger = logging.getLogger(__name__)

# All time, then the shared activity periods — the same window vocabulary the
# entity-activity tables use.
ALL_TIME = "all"

PR_RESPONSIVENESS_FILE = "pr_responsiveness.csv"
PR_RESPONSIVENESS_BY_REPO_FILE = "pr_responsiveness_by_repo.csv"
PR_RESPONSIVENESS_MONTHLY_FILE = "pr_responsiveness_monthly.csv"


def main(org: str = ORG) -> None:
    """Write the PR-responsiveness tables for ``org``."""
    client, org_data_dir, _charts_dir = org_context(org)
    records = load_contributor_activity(client, org)
    events = combined_activity_events(records)
    prs = pr_response_times(events)
    logger.info("PR responsiveness for %s from %d merged pull requests", org, len(prs))

    # One moment ends every window, and it is written into the tables so a
    # reader can state the exact dates each window covers.
    now = datetime.now(UTC)
    windows = [(ALL_TIME, None), *((period.key, period.cutoff(now)) for period in ACTIVITY_PERIODS)]
    latest = events["occurred_at"].max() if not events.empty else None
    stamps = {"window_end": now.isoformat(), "data_through": latest.isoformat() if latest is not None else None}

    overall = responsiveness_summary(prs, windows).assign(**stamps)
    by_repo = responsiveness_summary(prs, windows, by_repo=True).assign(**stamps)

    # Keep complete tables for consumers that need every reporting window.
    save_dataframe(overall, org_data_dir / PR_RESPONSIVENESS_FILE)
    save_dataframe(by_repo, org_data_dir / PR_RESPONSIVENESS_BY_REPO_FILE)
    save_dataframe(monthly_responsiveness(prs), org_data_dir / PR_RESPONSIVENESS_MONTHLY_FILE)

    # Period tabs use one file per period; the filename carries the selection.
    for period in ACTIVITY_PERIODS:
        for frame, filename in (
            (overall, PR_RESPONSIVENESS_FILE),
            (by_repo, PR_RESPONSIVENESS_BY_REPO_FILE),
        ):
            selected = frame.loc[frame["period"] == period.key].drop(columns=["period"])
            stem = filename.removesuffix(".csv")
            save_dataframe(selected, org_data_dir / period.filename(stem))
