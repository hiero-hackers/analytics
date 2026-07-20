"""
This module provides functions to search for issues on GitHub using the REST API.

It supports pagination to handle large result sets and allows for complex search queries using GitHub's search syntax.
"""

from __future__ import annotations

import base64
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import yaml

from hiero_analytics.config.github import SEARCH_REQUEST_DELAY_SECONDS

from .github_client import GitHubClient
from .models import RunnerRecord, SearchIssueRecord
from .pagination import paginate_page_number

logger = logging.getLogger(__name__)

# GitHub's Search API serves at most 1000 results per query; requesting
# beyond that returns 422, so pagination must stop at this boundary.
SEARCH_RESULT_LIMIT = 1000
_SEARCH_PAGE_SIZE = 100
_SEARCH_MAX_PAGES = SEARCH_RESULT_LIMIT // _SEARCH_PAGE_SIZE


GITHUB_HOSTED_PATTERNS = [
    r"^ubuntu-.*",
    r"^windows-.*",
    r"^macos-.*",
]

GITHUB_HOSTED_EXACT = {
    "ubuntu-latest",
    "windows-latest",
    "macos-latest",
}


def search_issues(
    client: GitHubClient,
    query: str,
    *,
    max_pages: int | None = None,
) -> list[SearchIssueRecord]:
    """
    Search GitHub issues and pull requests using the REST search API.

    Args:
        client: Authenticated GitHub client.
        query: GitHub search query string.
        max_pages: Optional cap on the number of pages to request.

    Returns:
        Normalized :class:`SearchIssueRecord` items. Results are capped at
        GitHub's 1000-result search limit; a warning is logged when a query
        matches more than that.
    """
    truncation_logged = False

    def page(page_number: int) -> list[SearchIssueRecord]:

        params = {
            "q": query,
            "per_page": _SEARCH_PAGE_SIZE,
            "page": page_number,
        }

        data = client.get(
            "https://api.github.com/search/issues",
            params=params,
        )

        nonlocal truncation_logged
        total_count = data.get("total_count")
        if not truncation_logged and isinstance(total_count, int) and total_count > SEARCH_RESULT_LIMIT:
            truncation_logged = True
            logger.warning(
                "Search query matched %d results but GitHub serves only the first %d: %s",
                total_count,
                SEARCH_RESULT_LIMIT,
                query,
            )
        if data.get("incomplete_results"):
            logger.warning(
                "GitHub flagged search results as incomplete (query timed out) on page %d: %s",
                page_number,
                query,
            )

        items = data.get("items", [])

        records = (SearchIssueRecord.from_search_item(item) for item in items if isinstance(item, dict))
        return [record for record in records if record is not None]

    effective_max_pages = _SEARCH_MAX_PAGES if max_pages is None else min(max_pages, _SEARCH_MAX_PAGES)

    return paginate_page_number(
        page,
        max_pages=effective_max_pages,
        delay_seconds=SEARCH_REQUEST_DELAY_SECONDS,
    )


def has_codeowners_file(client: GitHubClient, org: str, repo: str) -> bool:
    """Checks for the existence of a CODEOWNERS file in standard repository locations.

    Only a 404 counts as "not present"; any other error propagates so that a
    network or rate-limit failure is never reported as a missing CODEOWNERS file.
    """
    paths = [".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"]

    for path in paths:
        logger.info(f"Fetching CODEOWNERS for {repo} at {path}")

        url = f"https://api.github.com/repos/{org}/{repo}/contents/{path}"
        try:
            response = client.get(url)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                continue
            raise

        if response:
            return True

    return False


def _is_self_hosted(label: str) -> bool | None:
    """
    Determines if a runner is self-hosted.

    Returns:
        True: Explicitly a custom/self-hosted runner.
        False: Explicitly a standard GitHub-hosted runner.
        None: Indeterminate (complex expressions/matrix variables).
    """
    label_value = str(label).lower().strip()

    if label_value in GITHUB_HOSTED_EXACT or any(re.match(p, label_value) for p in GITHUB_HOSTED_PATTERNS):
        return False

    if "${{" in label_value:
        return None

    return True


def _process_workflow_file(client: GitHubClient, wf: dict, repo: str) -> list[RunnerRecord]:
    """Process a single yml file and extract job/runner records."""
    results: list[RunnerRecord] = []
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

            for label_value in labels:
                status = _is_self_hosted(str(label_value))

                if status is True:
                    final_status = True
                    break
                if status is None:
                    final_status = None

            results.append(
                RunnerRecord(
                    repo=repo,
                    workflow_file=wf["name"],
                    job_name=job_name,
                    runner=str(runs_on),
                    is_self_hosted=final_status,
                )
            )
    except requests.RequestException:
        raise  # network/API failures must not read as "no runners in this file"
    except Exception as e:
        # A malformed workflow file is data, not an infrastructure failure —
        # skip it loudly rather than failing the whole repo scan.
        logger.error(f"Failed to parse {wf['name']}: {e}")

    return results


def fetch_repo_workflows(client: GitHubClient, org: str, repo: str) -> list[RunnerRecord]:
    """Fetch per-job runner records for a repository's workflow files.

    Only a 404 counts as "no workflow directory"; any other error propagates so
    a transient/network/permission failure is never misreported as a repo with
    no runners.
    """
    url = f"https://api.github.com/repos/{org}/{repo}/contents/.github/workflows"
    try:
        workflows = client.get(url)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            logger.debug("No workflow directory in %s", repo)
            return []
        raise

    if not isinstance(workflows, list):
        return []

    yaml_files = [wf for wf in workflows if wf["name"].endswith((".yml", ".yaml"))]

    all_job_results: list[RunnerRecord] = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_process_workflow_file, client, wf, repo): wf for wf in yaml_files}
        for future in as_completed(futures):
            res = future.result()
            if res:
                all_job_results.extend(res)

    return all_job_results
