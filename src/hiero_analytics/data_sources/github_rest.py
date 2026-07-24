"""GitHub REST helpers for CODEOWNERS presence and Actions-runner classification.

CODEOWNERS existence checks and workflow-YAML runner scanning via the REST API
(the GraphQL ingestion lives in ``github_ingest``).
"""

from __future__ import annotations

import base64
import logging
import re

import requests
import yaml

from .github_client import GitHubClient
from .github_ingest._common import fetch_all_with_retry
from .models import RunnerRecord

logger = logging.getLogger(__name__)

GITHUB_HOSTED_PATTERNS = [
    r"^ubuntu-.*",
    r"^windows-.*",
    r"^macos-.*",
]

# Concurrency for fetching one repo's workflow files (small, file-count-bound).
_WORKFLOW_FETCH_WORKERS = 10

GITHUB_HOSTED_EXACT = {
    "ubuntu-latest",
    "windows-latest",
    "macos-latest",
}


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

    # The shared fan-out retries transient failures once and raises
    # PartialOrgFetchError rather than returning a silently partial scan.
    return fetch_all_with_retry(
        yaml_files,
        _WORKFLOW_FETCH_WORKERS,
        lambda wf: _process_workflow_file(client, wf, repo),
        task_desc=f"workflow files ({repo})",
        describe=lambda wf: str(wf.get("name", "?")),
    )
