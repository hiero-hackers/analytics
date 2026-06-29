"""Issue timeline / events ingestion via the REST API.

These use the REST ``/timeline`` and ``/issues/events`` endpoints (GraphQL does
not expose the same event stream) and feed the issue-event analyses. The
``*_since`` variants stop paginating once they reach events older than the cutoff.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import requests

from hiero_analytics.config.github import BASE_URL

from ..cache import load_records_cache, save_records_cache
from ..github_client import GitHubClient
from ..models import IssueRecord, IssueTimelineEventRecord
from ._common import _cache_kwargs

logger = logging.getLogger(__name__)

_ISSUE_TIMELINE_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def fetch_repo_issue_timeline_events_rest(
    client: GitHubClient,
    owner: str,
    repo: str,
    issue_number: int,
    *,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
) -> list[IssueTimelineEventRecord]:
    """Fetch REST timeline events for one issue."""
    cache_scope = f"{owner}_{repo}_{issue_number}"
    cache_parameters = {
        "owner": owner,
        "repo": repo,
        "issue_number": issue_number,
    }
    cached = load_records_cache(
        "repo_issue_timeline_events",
        cache_scope,
        cache_parameters,
        IssueTimelineEventRecord,
        use_cache=use_cache,
        ttl_seconds=cache_ttl_seconds,
        refresh=refresh,
    )
    if cached is not None:
        return cached

    records: list[IssueTimelineEventRecord] = []
    page = 1

    while True:
        payload = client.get(
            f"{BASE_URL}/repos/{owner}/{repo}/issues/{issue_number}/timeline",
            params={"per_page": 100, "page": page},
            headers=_ISSUE_TIMELINE_HEADERS,
        )

        if not isinstance(payload, list):
            raise ValueError("Issue timeline payload must be a list")

        for event in payload:
            if not isinstance(event, dict):
                continue

            record = IssueTimelineEventRecord.from_rest_event(
                event,
                owner=owner,
                repo=repo,
                issue_number=issue_number,
            )
            if record is not None:
                records.append(record)

        if len(payload) < 100:
            break

        page += 1

    save_records_cache(
        "repo_issue_timeline_events",
        cache_scope,
        cache_parameters,
        IssueTimelineEventRecord,
        records,
        use_cache=use_cache,
    )
    return records


def fetch_issue_timeline_events_rest(
    client: GitHubClient,
    issues: list[IssueRecord],
    *,
    max_workers: int = 8,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
) -> list[IssueTimelineEventRecord]:
    """Fetch timeline events for a provided issue collection in parallel."""
    unique_issues = {(issue.repo, issue.number): issue for issue in issues}

    def fetch_func(issue: IssueRecord) -> list[IssueTimelineEventRecord]:
        """Fetch timeline events for a single issue."""
        owner, repo = issue.repo.split("/", maxsplit=1)
        return fetch_repo_issue_timeline_events_rest(
            client,
            owner,
            repo,
            issue.number,
            **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
        )

    records: list[IssueTimelineEventRecord] = []
    issue_items = list(unique_issues.values())

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_func, issue): issue for issue in issue_items}
        for future in as_completed(futures):
            issue = futures[future]
            try:
                records.extend(future.result())
            except Exception as exc:
                logger.exception(
                    "Failed fetching issue timeline events for %s#%s: %s",
                    issue.repo,
                    issue.number,
                    exc,
                )

    return records


def fetch_repo_issue_events_rest_since(
    client: GitHubClient,
    owner: str,
    repo: str,
    *,
    since: datetime,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
) -> list[IssueTimelineEventRecord]:
    """Fetch repository issue events since a cutoff date."""
    max_pages = 300
    cutoff = since.astimezone(UTC)
    cutoff_iso = cutoff.isoformat()
    cache_scope = f"{owner}_{repo}"
    cache_parameters = {
        "owner": owner,
        "repo": repo,
        "since": cutoff_iso,
    }
    cached = load_records_cache(
        "repo_issue_events_since",
        cache_scope,
        cache_parameters,
        IssueTimelineEventRecord,
        use_cache=use_cache,
        ttl_seconds=cache_ttl_seconds,
        refresh=refresh,
    )
    if cached is not None:
        return cached

    records: list[IssueTimelineEventRecord] = []
    page = 1

    while True:
        if page > max_pages:
            logger.warning(
                "Stopping issue event pagination for %s/%s after %d pages",
                owner,
                repo,
                max_pages,
            )
            break

        try:
            payload = client.get(
                f"{BASE_URL}/repos/{owner}/{repo}/issues/events",
                params={"per_page": 100, "page": page},
                headers=_ISSUE_TIMELINE_HEADERS,
            )
        except requests.HTTPError as exc:
            response = exc.response
            if response is not None and response.status_code == 422:
                logger.warning(
                    "Stopping issue event pagination for %s/%s at page %d due to 422",
                    owner,
                    repo,
                    page,
                )
                break
            raise

        if not isinstance(payload, list):
            raise ValueError("Repository issue events payload must be a list")

        page_has_older_events = False

        for event in payload:
            if not isinstance(event, dict):
                continue

            issue_node = event.get("issue")
            if not isinstance(issue_node, dict):
                continue

            issue_number = issue_node.get("number")
            if not isinstance(issue_number, int):
                continue

            record = IssueTimelineEventRecord.from_rest_event(
                event,
                owner=owner,
                repo=repo,
                issue_number=issue_number,
            )
            if record is None:
                continue

            occurred_at = record.occurred_at.astimezone(UTC)
            if occurred_at < cutoff:
                page_has_older_events = True
                continue

            records.append(record)

        if len(payload) < 100 or page_has_older_events:
            break

        page += 1

    save_records_cache(
        "repo_issue_events_since",
        cache_scope,
        cache_parameters,
        IssueTimelineEventRecord,
        records,
        use_cache=use_cache,
    )
    return records


def fetch_repo_issue_events_for_issues_since(
    client: GitHubClient,
    issues: list[IssueRecord],
    *,
    since: datetime,
    max_workers: int = 5,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
) -> list[IssueTimelineEventRecord]:
    """Fetch repository-level issue events since a cutoff for repos present in the issue set."""
    repos = sorted({issue.repo for issue in issues})

    def fetch_func(full_repo: str) -> list[IssueTimelineEventRecord]:
        """Fetch timeline events for all issues in a repository."""
        owner, repo = full_repo.split("/", maxsplit=1)
        return fetch_repo_issue_events_rest_since(
            client,
            owner,
            repo,
            since=since,
            **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
        )

    records: list[IssueTimelineEventRecord] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_func, full_repo): full_repo for full_repo in repos}
        for future in as_completed(futures):
            full_repo = futures[future]
            try:
                records.extend(future.result())
            except Exception as exc:
                logger.exception(
                    "Failed fetching repository issue events for %s since %s: %s",
                    full_repo,
                    since.isoformat(),
                    exc,
                )

    return records
