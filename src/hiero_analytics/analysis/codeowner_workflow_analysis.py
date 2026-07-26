"""Analysis functions for CODEOWNERS compliance and GitHub Actions runner workflows."""

import logging

import pandas as pd

from hiero_analytics.analysis.dataframe_utils import records_to_dataframe
from hiero_analytics.data_sources.models import CodeOwnersRecord, RunnerRecord

logger = logging.getLogger(__name__)


def prepare_org_codeowners_summary(codeowners: list[CodeOwnersRecord]) -> pd.DataFrame:
    """Aggregates CODEOWNERS presence into an organization level summary."""
    if not codeowners:
        return pd.DataFrame(columns=["status", "count"])

    present_count = sum(1 for r in codeowners if r.status)
    missing_count = len(codeowners) - present_count

    return pd.DataFrame({"status": ["Present", "Missing"], "count": [present_count, missing_count]})


def prepare_repo_level_codeowner_summary(codeowners: list[CodeOwnersRecord]) -> pd.DataFrame:
    """Per-repository CODEOWNERS presence, repos lacking a file first.

    The gap is the actionable part of this table, so it leads; repositories
    that already have a file need no attention and sort after it.
    """
    frame = records_to_dataframe(
        codeowners,
        lambda r: {"repo": r.repo, "status": r.status},
        ["repo", "status"],
    )
    if frame.empty:
        return frame
    return frame.sort_values(["status", "repo"], ascending=[True, True]).reset_index(drop=True)


def runner_records_to_dataframe(runners: list[RunnerRecord]) -> pd.DataFrame:
    """Converts a list of RunnerRecords into DataFrame."""
    return records_to_dataframe(
        runners,
        lambda r: {
            "repo": r.repo,
            "job": r.job_name,
            "runner": r.runner,
            "self_hosted": r.is_self_hosted,
        },
        ["repo", "job", "runner", "self_hosted"],
    )


def prepare_stacked_runner_summary(runners: list[RunnerRecord]) -> pd.DataFrame:
    """Aggregates runner type counts per repository for stacked bar chart visualization."""
    if not runners:
        return pd.DataFrame(columns=["repo", "Self-Hosted", "Standard", "Indeterminate"])

    counts = {}
    for r in runners:
        if r.repo not in counts:
            counts[r.repo] = {"repo": r.repo, "Self-Hosted": 0, "Standard": 0, "Indeterminate": 0}

        if r.is_self_hosted is True:
            key = "Self-Hosted"
        elif r.is_self_hosted is False:
            key = "Standard"
        else:
            key = "Indeterminate"

        counts[r.repo][key] += 1

    # Every per-repo dict seeds all three keys, so no column back-fill is needed.
    return pd.DataFrame(list(counts.values()))
