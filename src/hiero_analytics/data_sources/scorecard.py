"""Client for fetching OpenSSF Scorecard results from the public scorecard.dev API."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import requests

from hiero_analytics.config.github import HTTP_TIMEOUT_SECONDS
from hiero_analytics.data_sources.models import ScorecardRecord

logger = logging.getLogger(__name__)

SCORECARD_API = os.getenv("SCORECARD_API", "https://api.scorecard.dev/projects/github.com/hiero-ledger")


def fetch_repo_scorecard(repo: str) -> ScorecardRecord | None:
    """
    Fetch latest OpenSSF Scorecard for a repository.

    Args:
        repo: Repository in format `eg: hiero-python-sdk`

    Returns:
        ScorecardRecord, or None when the repository has no scorecard (404).

    Raises:
        requests.RequestException: On network failures or non-404 HTTP errors,
            so a transient outage is never silently recorded as a missing scorecard.
    """
    url = f"{SCORECARD_API}/{repo}"

    try:
        response = requests.get(url, timeout=HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            logger.debug("Scorecard not found for %s", repo)
            return None
        raise

    return _normalize_scorecard_response(repo, response.json())


def _normalize_scorecard_response(repo: str, json: dict[str, Any]) -> ScorecardRecord:
    """Normalize raw API response into ScorecardRecord."""
    score = float(json["score"])
    created_date = datetime.fromisoformat(str(json["date"]).replace("Z", "+00:00"))
    checks: dict[str, int] = {}

    for check in json["checks"]:
        if not isinstance(check, dict):
            continue

        checks[check["name"]] = check["score"]

    return ScorecardRecord(repo, score, checks, created_date)
