"""Build the tables behind the repository and contributor detail views.

Reads the persisted org-wide activity datasets (pull requests, reviews, merges,
issues and label events — the same records the contributor profiles use) and
writes, per org, each repository's and each contributor's tracked actions for
the Week, 1 month and 1 year windows and all time, the activity of every
(repository, contributor) pair, and monthly trends. Every window is computed
from the events inside it, so counts such as distinct active contributors are
exact rather than summed from all-time profiles.

Offline-capable: it only reads datasets other pipelines persisted. The
``data_api`` step publishes these tables as the detail documents
(``export/entity_views``).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from hiero_analytics.analysis.contributor_activity_profile import combined_activity_events
from hiero_analytics.analysis.entity_activity import (
    contributor_activity,
    monthly_activity,
    repo_activity,
    repo_contributor_activity,
)
from hiero_analytics.config.paths import ORG
from hiero_analytics.dashboard_spec import entities as spec
from hiero_analytics.domain.periods import ACTIVITY_PERIODS
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.pipelines._shared import load_contributor_activity, load_issue_label_events, org_context

logger = logging.getLogger(__name__)

# All time, then the shared activity periods. "all" names the all-time rows in
# these long-form tables only; the published documents keep the API's
# convention of all-time as the base with period variants beside it.
ALL_TIME = "all"


def main(org: str = ORG) -> None:
    """Write the entity-activity tables for ``org``."""
    client, org_data_dir, _ = org_context(org)
    records = load_contributor_activity(client, org)
    label_events = load_issue_label_events(client, org)
    events = combined_activity_events(records, label_events)
    logger.info("Entity activity for %s from %d tracked events", org, len(events))

    # One moment ends every window, and it is written into the tables so the
    # published documents can state the exact dates each window covers.
    now = datetime.now(UTC)
    windows = [(ALL_TIME, None), *((period.key, period.cutoff(now)) for period in ACTIVITY_PERIODS)]
    tables = {
        spec.REPO_ACTIVITY_FILE: repo_activity(events, windows),
        spec.CONTRIBUTOR_ACTIVITY_FILE: contributor_activity(events, windows),
        spec.PAIR_ACTIVITY_FILE: repo_contributor_activity(events, windows),
    }
    # The latest event recorded anywhere in the org: when it is well before the
    # window end, the activity datasets are behind and recent windows undercount.
    latest = events["occurred_at"].max() if not events.empty else None
    stamps = {"window_end": now.isoformat(), "data_through": latest.isoformat() if latest is not None else None}
    for name, frame in tables.items():
        save_dataframe(frame.assign(**stamps), org_data_dir / name)
    save_dataframe(monthly_activity(events, "repo"), org_data_dir / spec.REPO_MONTHLY_FILE)
    save_dataframe(monthly_activity(events, "contributor"), org_data_dir / spec.CONTRIBUTOR_MONTHLY_FILE)

    repos = tables[spec.REPO_ACTIVITY_FILE]
    contributors = tables[spec.CONTRIBUTOR_ACTIVITY_FILE]
    logger.info(
        "Entity activity: %d repositories, %d contributors",
        repos.loc[repos["period"] == ALL_TIME, "repo"].nunique(),
        contributors.loc[contributors["period"] == ALL_TIME, "contributor"].nunique(),
    )
