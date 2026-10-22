"""Build the contributor-activity heatmap table for an organization.

Orchestration only: it reuses the persisted org-wide contributor-activity dataset
(populated earlier in ``run_all``, so no extra GitHub fetch when present), builds
the weighted monthly matrix (:mod:`analysis.contributor_heatmap`) and saves it as
a CSV. The ranked, score-based companion to the descriptive profiles and
networks in ``contributor_activity``.

Org-independent: a governed org's contributors are labelled by their governance
role; an ungoverned org's config is empty, so its heatmap carries no role
labels and is otherwise identical. The full run schedules it once per rendered
org (``run_all``), so this module never loops over orgs itself.
"""

from __future__ import annotations

import logging

from hiero_analytics.analysis.contributor_heatmap import build_activity_heatmap_dataframe
from hiero_analytics.config.paths import ORG
from hiero_analytics.data_sources.governance_config import build_repo_role_lookup, fetch_governance_config
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.pipelines._shared import load_contributor_activity, org_context

logger = logging.getLogger(__name__)


def main(org: str = ORG) -> None:
    """Build the contributor-activity heatmap for ``org``."""
    client, org_data_dir = org_context(org)
    repo_role_lookup = build_repo_role_lookup(fetch_governance_config(org), org=org)

    records = load_contributor_activity(client, org)
    logger.info("Using %d activity records for the %s heatmap", len(records), org)

    heatmap_df = build_activity_heatmap_dataframe(records, repo_role_lookup)
    save_dataframe(heatmap_df, org_data_dir / "contributor_activity_heatmap.csv")
    logger.info("Contributor activity heatmap complete for %s (%d contributors)", org, len(heatmap_df))
