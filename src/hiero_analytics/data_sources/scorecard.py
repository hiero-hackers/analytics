from __future__ import annotations

import logging
import os
from typing import Any

import requests

from hiero_analytics.config.github import HTTP_TIMEOUT_SECONDS
from hiero_analytics.data_sources.models import ScorecardRecord

logger = logging.getLogger(__name__)

SCORECARD_API = os.getenv(
  "SCORECARD_API",
  "https://api.scorecard.dev/projects/github.com/hiero-ledger"
)

def fetch_repo_scorecard(repo: str) -> ScorecardRecord:
    """
    Fetch latest OpenSSF Scorecard for a repository.
    
    Args:
        repo: Repository in format `eg: hiero-python-sdk`
  
    Returns:
        ScorecardRecord if available, else None
    """
    url = f"{SCORECARD_API}/{repo}"

    try:
        response = requests.get(url, timeout=HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
        
        json_data = response.json()
        return _normalize_scorecard_response(repo, json_data)

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logger.debug("Scorecard not found for %s", repo)
            return None

        logger.error("HTTP error for %s: %s", repo, e)
        return None

    except requests.exceptions.RequestException as e:
        logger.error("Network error while fetching scorecard %s: %s", repo, e)
        return None


def _normalize_scorecard_response(repo:str, json: dict[str, Any]) -> ScorecardRecord:
    """
    Normalize raw API response into ScorecardRecord.
    """
    score = float(json["score"])
    created_date = json["date"]
    checks: dict[str, int] = {}

    for check in json["checks"]:
        if not isinstance(check, dict):
            continue
    
        checks[check["name"]] = check["score"]

    return ScorecardRecord(repo, score, checks, created_date)
