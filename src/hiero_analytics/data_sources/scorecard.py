"""Client for fetching OpenSSF Scorecard results from the public scorecard.dev API."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

from hiero_analytics.config.github import HTTP_TIMEOUT_SECONDS
from hiero_analytics.data_sources.models import ScorecardRecord

from .serialization import parse_github_datetime

logger = logging.getLogger(__name__)

# Override for a mirror or test server. The value must carry an ``{org}``
# placeholder: an older org-less value (``…/github.com/hiero-ledger``) would
# query that one org's scorecards for every org, so it is rejected, not reused.
SCORECARD_API = os.getenv("SCORECARD_API", "https://api.scorecard.dev/projects/github.com/{org}")


def scorecard_url(repo: str, org: str, template: str | None = None) -> str:
    """The Scorecard API URL for ``org/repo``; raises when the template has no ``{org}``."""
    template = SCORECARD_API if template is None else template
    if "{org}" not in template:
        raise ValueError(f"SCORECARD_API must contain an {{org}} placeholder, got {template!r}")
    return f"{template.replace('{org}', org)}/{repo}"


def fetch_repo_scorecard(repo: str, *, org: str = "hiero-ledger") -> ScorecardRecord | None:
    """
    Fetch latest OpenSSF Scorecard for a repository.

    Args:
        repo: Repository in format `eg: hiero-python-sdk`
        org: GitHub organisation that owns the repository.

    Returns:
        ScorecardRecord, or None when the repository has no scorecard (404).

    Raises:
        requests.RequestException: On network failures or non-404 HTTP errors,
            so a transient outage is never silently recorded as a missing scorecard.
    """
    url = scorecard_url(repo, org)

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
    created_date = parse_github_datetime(str(json["date"]), strict=True)
    checks: dict[str, int] = {}

    for check in json["checks"]:
        if not isinstance(check, dict):
            continue

        checks[check["name"]] = check["score"]

    return ScorecardRecord(repo, score, checks, created_date)
