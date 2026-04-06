import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

import pandas as pd
import yaml

from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.models import CodeOwnersRecord, RunnerRecord

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


STANDARD_RUNNER_PREFIXES = ("ubuntu-", "windows-", "macos-")
STANDARD_EXACT_NAMES = {"ubuntu-latest", "windows-latest", "macos-latest"}


def has_codeowners_file(client: GitHubClient, org: str, repo: str) -> bool:
    """Checks for the existence of a CODEOWNERS file in standard repository locations."""
    paths = [".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"]
    for path in paths:
        logger.info(f"Fetching CODEOWNERS for {repo} at {path}")

        try:
            url = f"https://api.github.com/repos/{org}/{repo}/contents/{path}"
            response = client.get(url)

            if response:
                return True
        except Exception:
            continue
    
    return False


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

def _is_standard_runner(label: str) -> bool:
    """Helper to validate if runner is a standard gitHub runner."""
    l = label.lower().strip()
    if l in STANDARD_EXACT_NAMES:
        return True

    return False


def _process_workflow_file(client: GitHubClient, wf: dict) -> list[dict]:
    """Process a single yml file and extract job/runner details."""
    results = []

    try:
        resp = client.get(wf["url"])
        if not (resp and "content" in resp):
            return []

        raw = base64.b64decode(resp["content"]).decode("utf-8")
        data = yaml.safe_load(raw)
        
        jobs = data.get("jobs", {})
        if not isinstance(jobs, dict):
            return []

        for job_id, job_cfg in jobs.items():
            if not isinstance(job_cfg, dict): continue
            
            job_name = job_cfg.get("name", job_id)
            runs_on = job_cfg.get("runs-on")
            
            if not runs_on:
                continue

            labels = [str(runs_on)] if isinstance(runs_on, (str, int)) else [str(l) for l in runs_on]
            
            is_sh = False
            detected_label = str(runs_on)
            
            for l in labels:
                l_lower = l.lower()
                if "self-hosted" in l_lower or not _is_standard_runner(l_lower):
                    is_sh = True
                    detected_label = l
                    break
            
            results.append({
                "file": wf["name"],
                "job": job_name,
                "runner": detected_label,
                "is_self_hosted": is_sh
            })
    except Exception as e:
        logger.error(f"Failed to parse {wf['name']}: {e}")
    
    return results



def fetch_repo_workflows(client: GitHubClient, org: str, repo: str) -> list[dict]:
    """Fetches workflows using threading for speed."""
    all_job_results = []
    try:
        url = f"https://api.github.com/repos/{org}/{repo}/contents/.github/workflows"
        workflows = client.get(url)
        
        if not isinstance(workflows, list):
            return []

        yaml_files = [wf for wf in workflows if wf["name"].endswith((".yml", ".yaml"))]

        # Use ThreadPoolExecutor to handle the I/O bound GitHub API calls
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(_process_workflow_file, client, wf): wf for wf in yaml_files}
            for future in as_completed(futures):
                res = future.result()
                if res:
                    all_job_results.extend(res)

    except Exception as e:
        logger.debug(f"Workflow directory not found or error in {repo}: {e}")
    
    return all_job_results


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
        return pd.DataFrame(columns=["repo", "job", "runner", "self_hosted"])

    counts = {}
    for r in runners:
        if r.repo not in counts:
            counts[r.repo] = {"repo": r.repo, "Self-Hosted": 0, "Standard": 0}
        
        key = "Self-Hosted" if r.is_self_hosted else "Standard"
        counts[r.repo][key] += 1

    summary = pd.DataFrame(list(counts.values()))

    if not summary.empty:
        if "Self-Hosted" not in summary.columns: summary["Self-Hosted"] = 0
        if "Standard" not in summary.columns: summary["Standard"] = 0
        
    return summary