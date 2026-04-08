"""
This module provides functions to search for issues on GitHub using the REST API. 
It supports pagination to handle large result sets and allows for complex search queries using GitHub's search syntax.
"""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import re
from typing import Any

import yaml

from .github_client import GitHubClient
from .pagination import paginate_page_number

logger = logging.getLogger(__name__)


GITHUB_HOSTED_PATTERNS = [
    r"^ubuntu-.*",
    r"^windows-.*",
    r"^macos-.*",
]

GITHUB_HOSTED_EXACT = {
    "ubuntu-latest", "windows-latest", "macos-latest",
}


def search_issues(
    client: GitHubClient,
    query: str,
) -> list[dict[str, Any]]:
    """
    Search GitHub issues and pull requests using the REST search API.

    Args:
        client: Authenticated GitHub client.
        query: GitHub search query string.

    Returns:
        A list of issue objects returned by the GitHub API.
    """

    def page(page_number: int) -> list[dict[str, Any]]:

        params = {
            "q": query,
            "per_page": 100,
            "page": page_number,
        }

        data = client.get(
            "https://api.github.com/search/issues",
            params=params,
        )

        items = data.get("items", [])

        return [item for item in items if isinstance(item, dict)]

    return paginate_page_number(page)

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


def _is_self_hosted(label: str) -> bool | None:
    """
    Determines if a runner is self-hosted.
    Returns:
        True: Explicitly a custom/self-hosted runner.
        False: Explicitly a standard GitHub-hosted runner.
        None: Indeterminate (complex expressions/matrix variables).
    """
    l = str(label).lower().strip()

    if l in GITHUB_HOSTED_EXACT or any(re.match(p, l) for p in GITHUB_HOSTED_PATTERNS):
        return False

    if "${{" in l:
        return None

    return True


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
            if not isinstance(job_cfg, dict): 
                continue
            
            job_name = job_cfg.get("name", job_id)
            runs_on = job_cfg.get("runs-on")
            if not runs_on:
                continue

            labels = [runs_on] if isinstance(runs_on, (str, int)) else runs_on
            
            final_status = False 
            
            for l in labels:
                status = _is_self_hosted(str(l))
                
                if status is True:
                    final_status = True
                    break 
                elif status is None:
                    final_status = None

            results.append({
                "file": wf["name"],
                "job": job_name,
                "runner": str(runs_on),
                "is_self_hosted": final_status
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

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(_process_workflow_file, client, wf): wf for wf in yaml_files}
            for future in as_completed(futures):
                res = future.result()
                if res:
                    all_job_results.extend(res)

    except Exception as e:
        logger.debug(f"Workflow directory not found or error in {repo}: {e}")
    
    return all_job_results