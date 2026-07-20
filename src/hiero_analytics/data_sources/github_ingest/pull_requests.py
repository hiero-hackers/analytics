"""Merged pull-request difficulty ingestion via the GraphQL API.

Links merged PRs to the issues they close, repo- and org-wide. The org-level
fetcher is incremental: the persistent dataset store keeps the full history and
later runs fetch only PRs updated since the watermark.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from hiero_analytics.config.github import GITHUB_MAX_WORKERS
from hiero_analytics.config.paths import dataset_path, load_query

from ..dataset_store import PartialOrgFetchError, fetch_incremental
from ..github_client import GitHubClient
from ..models import PullRequestDifficultyRecord
from ..pagination import extract_graphql_cursor_page, paginate_cursor
from ._common import (
    _cache_kwargs,
    _parse_graphql_datetime,
    fetch_github_resource,
)
from .batched import fetch_org_records_batched

logger = logging.getLogger(__name__)


def fetch_repo_merged_pr_difficulty_graphql(
    client: GitHubClient,
    owner: str,
    repo: str,
    *,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
) -> list[PullRequestDifficultyRecord]:
    """Fetch merged pull requests and their linked closing issues for a repository."""
    MERGED_PR_QUERY = load_query("merged_pr")
    return fetch_github_resource(
        client,
        MERGED_PR_QUERY,
        {"owner": owner, "repo": repo},
        PullRequestDifficultyRecord,
        ["repository", "pullRequests"],
        cache_key="repo_merged_pr_difficulty",
        cache_scope=f"{owner}_{repo}",
        cache_parameters={"owner": owner, "repo": repo},
        context_builder=lambda _node: {"owner": owner, "repo": repo},
        **_cache_kwargs(use_cache, cache_ttl_seconds, refresh),
    )


def fetch_repo_merged_prs_since_graphql(
    client: GitHubClient,
    owner: str,
    repo: str,
    since: datetime,
) -> list[PullRequestDifficultyRecord]:
    """Fetch merged PRs updated at/after ``since`` (an incremental delta).

    ``pullRequests`` has no ``filterBy: since``, but the query orders by
    ``UPDATED_AT`` descending, so pagination stops at the first page containing a
    PR older than ``since``. Boundary-page records older than ``since`` are still
    returned — the incremental merge is an idempotent upsert, so re-sending them
    is harmless. Never cached — deltas change every run.
    """
    query = load_query("merged_pr")

    def page(cursor: str | None) -> tuple[list[PullRequestDifficultyRecord], str | None, bool]:
        """Fetch a single page of merged PRs, stopping past the cutoff."""
        data = client.graphql(query, {"owner": owner, "repo": repo, "cursor": cursor})
        nodes, next_cursor, has_next = extract_graphql_cursor_page(data, ["repository", "pullRequests"])

        records: list[PullRequestDifficultyRecord] = []
        page_has_older_prs = False
        for node in nodes:
            updated_at = _parse_graphql_datetime(node.get("updatedAt"))
            if updated_at is not None and updated_at < since:
                page_has_older_prs = True
            records.extend(PullRequestDifficultyRecord.from_github_node(node, {"owner": owner, "repo": repo}))

        return records, next_cursor, has_next and not page_has_older_prs

    return paginate_cursor(page)


def fetch_org_merged_pr_difficulty_graphql(
    client: GitHubClient,
    org: str,
    max_workers: int = GITHUB_MAX_WORKERS,
    *,
    refresh: bool = False,
) -> list[PullRequestDifficultyRecord]:
    """Fetch org merged-PR difficulty incrementally via the persistent dataset store.

    The first run does a full fetch; later runs fetch only PRs updated since the
    stored watermark (PRs carry ``updatedAt``) and merge them in. Relabeling a
    linked issue does not bump the PR's ``updatedAt``, and unlinked (pr, issue)
    rows are upsert-only — both heal on the periodic full refresh.
    ``refresh=True`` forces a full re-fetch (self-heal).
    """

    def full_fetch() -> list[PullRequestDifficultyRecord]:
        return fetch_org_records_batched(
            client,
            org,
            query_text=load_query("merged_pr"),
            model_class=PullRequestDifficultyRecord,
            nodes_path=["pullRequests"],
            per_repo=lambda repo: fetch_repo_merged_pr_difficulty_graphql(
                client, repo.owner, repo.name, use_cache=False
            ),
            task_desc="organization merged PR difficulty",
            max_workers=max_workers,
        )

    def since_fetch(since: datetime) -> list[PullRequestDifficultyRecord]:
        def older_than_since(node: dict) -> bool:
            updated_at = _parse_graphql_datetime(node.get("updatedAt"))
            return updated_at is not None and updated_at < since

        try:
            # Same query as the full fetch: PRs have no filterBy(since), so the
            # delta relies on UPDATED_AT-descending order plus an early stop.
            return fetch_org_records_batched(
                client,
                org,
                query_text=load_query("merged_pr"),
                model_class=PullRequestDifficultyRecord,
                nodes_path=["pullRequests"],
                stop_node=older_than_since,
                per_repo=lambda repo: fetch_repo_merged_prs_since_graphql(client, repo.owner, repo.name, since),
                task_desc="organization merged PR updates",
                max_workers=max_workers,
            )
        except PartialOrgFetchError:
            raise  # let the store hold the watermark; don't fall back to full
        except Exception:
            logger.exception("Incremental merged-PR fetch failed; falling back to full fetch")
            return full_fetch()

    return fetch_incremental(
        path=dataset_path("merged_pr_difficulty", org),
        model_class=PullRequestDifficultyRecord,
        key_of=lambda r: (r.repo, r.pr_number, r.issue_number),
        updated_at_of=lambda r: r.updated_at,
        full_fetch=full_fetch,
        since_fetch=since_fetch,
        force_full=refresh,
        full_refresh_after=timedelta(days=30),
    )
