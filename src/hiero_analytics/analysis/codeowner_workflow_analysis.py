import logging
import pandas as pd

from hiero_analytics.data_sources.models import CodeOwnersRecord, RunnerRecord

logger = logging.getLogger(__name__)


def prepare_org_codeowners_summary(codeowners: list[CodeOwnersRecord]) -> pd.DataFrame:
    """Aggregates CODEOWNERS presence into an organization level summary."""
    if not codeowners:
        return pd.DataFrame(columns=["status", "count"])
    

    present_count = sum(1 for r in codeowners if r.status)
    missing_count = len(codeowners) - present_count

    return pd.DataFrame({
        "status": ["Present", "Missing"],
        "count": [present_count, missing_count]
    })


def prepare_repo_level_codeowner_summary(codeowners: list[CodeOwnersRecord]) -> pd.DataFrame:
    """Transforms a list of CodeOwnersRecords into a repository level DataFrame"""
    if not codeowners:
        return pd.DataFrame(columns=["repo", "status"])

    return pd.DataFrame([
        {
            "repo": r.repo,
            "status": r.status
        }
        for r in codeowners
    ])


def runner_records_to_dataframe(runners: list[RunnerRecord]) -> pd.DataFrame:
    """Converts a list of RunnerRecords into DataFrame"""
    if not runners:
        return pd.DataFrame(columns=["repo", "job", "runner", "self_hosted"])
    
    return pd.DataFrame([
        {
            "repo": r.repo,
            "job": r.job_name,
            "runner": r.runner,
            "self_hosted": r.is_self_hosted
        }
        for r in runners
    ])

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

    summary = pd.DataFrame(list(counts.values()))

    for col in ["Self-Hosted", "Standard", "Indeterminate"]:
        if col not in summary.columns:
            summary[col] = 0
        
    return summary