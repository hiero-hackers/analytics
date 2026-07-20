"""Batched multi-repo GraphQL fetching via repository field aliases.

Instead of one query per repository, several repositories are combined into a
single request::

    query BatchedRepos($c0: String, $c1: String, $states: [IssueState!]) {
      r0: repository(owner: "org", name: "repo-a") { issues(after: $c0, ...) {...} }
      r1: repository(owner: "org", name: "repo-b") { issues(after: $c1, ...) {...} }
      rateLimit { ... }
    }

Each alias keeps its own cursor, so repositories page independently within the
batch and drop out as they complete. The rate-limit point cost is roughly the
sum of the individual queries, but round-trips collapse from one-per-repo-page
to one-per-batch-round — the dominant wall-clock win for org-wide fetches.

The single-repo ``queries/*.graphql`` files stay the source of truth: the
repository sub-selection is extracted from them here, so the batched and
per-repo paths can never drift apart.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

from hiero_analytics.config.github import GITHUB_GRAPHQL_BATCH_SIZE

from ..dataset_store import PartialOrgFetchError
from ..github_client import GitHubClient
from ..models import RepositoryRecord
from . import _common
from ._common import fetch_all_with_retry

logger = logging.getLogger(__name__)

_QUERY_HEADER_RE = re.compile(r"query\s+\w+\s*\(([^)]*)\)\s*\{")
_REPOSITORY_OPEN_RE = re.compile(r"repository\s*\(\s*owner:\s*\$owner\s*,\s*name:\s*\$repo\s*\)\s*\{")
_CURSOR_RE = re.compile(r"\$cursor\b")
# GitHub owner/repo names are restricted to these characters; anything else is
# refused rather than interpolated into query text.
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_PER_REPO_VARIABLES = {"owner", "repo", "cursor"}


def _matching_brace(text: str, open_index: int) -> int:
    """Index of the brace closing the one at ``open_index``."""
    depth = 0
    for index in range(open_index, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    raise ValueError("Unbalanced braces in GraphQL query")


def split_repo_query(query_text: str) -> tuple[list[str], str, str]:
    """Split a single-repo query into (shared declarations, repository body, fragments).

    Shared declarations are the query's variable declarations minus the per-repo
    ``$owner``/``$repo``/``$cursor``; the repository body is the selection inside
    ``repository(owner:$owner, name:$repo) { ... }``; fragments are whatever
    follows the query block (appended by ``load_query``).
    """
    header = _QUERY_HEADER_RE.search(query_text)
    if header is None:
        raise ValueError("Query has no parameterized header")
    declarations = [d.strip() for d in header.group(1).split(",") if d.strip()]
    shared = [d for d in declarations if d.lstrip("$").split(":", 1)[0].strip() not in _PER_REPO_VARIABLES]

    repo_open = _REPOSITORY_OPEN_RE.search(query_text)
    if repo_open is None:
        raise ValueError("Query has no repository(owner:$owner, name:$repo) selection")
    open_brace = repo_open.end() - 1
    body = query_text[open_brace + 1 : _matching_brace(query_text, open_brace)]

    query_close = _matching_brace(query_text, header.end() - 1)
    fragments = query_text[query_close + 1 :].strip()
    return shared, body, fragments


def _build_round_query(
    shared_declarations: list[str],
    body: str,
    fragments: str,
    batch: list[tuple[int, RepositoryRecord]],
) -> str:
    """Assemble one aliased multi-repo query for the given (index, repo) batch."""
    declarations = [f"$c{index}: String" for index, _ in batch] + shared_declarations
    sections = []
    for index, repo in batch:
        aliased_body = _CURSOR_RE.sub(f"$c{index}", body)
        sections.append(f'r{index}: repository(owner: "{repo.owner}", name: "{repo.name}") {{{aliased_body}}}')

    query = (
        f"query BatchedRepos({', '.join(declarations)}) {{\n"
        + "\n".join(sections)
        + "\nrateLimit{ limit remaining cost resetAt }\n}"
    )
    return f"{query}\n{fragments}" if fragments else query


def _fetch_chunk(
    client: GitHubClient,
    chunk: list[RepositoryRecord],
    shared_declarations: list[str],
    body: str,
    fragments: str,
    model_class: type,
    nodes_path: list[str],
    context_builder: Callable[[RepositoryRecord], dict],
    variables: dict | None,
    stop_node: Callable[[dict], bool] | None,
) -> tuple[list, list[RepositoryRecord]]:
    """Page one batch of repositories to completion.

    Returns ``(records, failed_repos)`` — a repository whose alias goes missing
    from a response, or whose pagination misbehaves (repeating cursor), joins
    ``failed_repos`` so the caller retries it individually rather than silently
    treating a partial repo as complete.
    """
    cursors: dict[int, str | None] = dict.fromkeys(range(len(chunk)))
    active = set(cursors)
    records: list = []
    failed: list[RepositoryRecord] = []

    while active:
        batch = [(index, chunk[index]) for index in sorted(active)]
        query = _build_round_query(shared_declarations, body, fragments, batch)
        round_variables = dict(variables or {})
        round_variables.update({f"c{index}": cursors[index] for index in sorted(active)})

        payload = client.graphql(query, round_variables).get("data") or {}

        for index, repo in batch:
            container: object = payload.get(f"r{index}")
            if not isinstance(container, dict):
                logger.warning("Repository %s missing from batched response; retrying it per-repo", repo.full_name)
                active.discard(index)
                failed.append(repo)
                continue
            for key in nodes_path:
                container = container.get(key) if isinstance(container, dict) else None
            if not isinstance(container, dict):
                active.discard(index)
                failed.append(repo)
                continue

            nodes = [node for node in (container.get("nodes") or []) if isinstance(node, dict)]
            context = context_builder(repo)
            for node in nodes:
                records.extend(model_class.from_github_node(node, context))

            page_info = container.get("pageInfo") or {}
            next_cursor = page_info.get("endCursor")
            reached_stop = stop_node is not None and any(stop_node(node) for node in nodes)
            if not page_info.get("hasNextPage") or not next_cursor or reached_stop:
                active.discard(index)
            elif next_cursor == cursors[index]:
                # A repeating cursor would loop forever; hand the repo to the
                # per-repo fallback instead of trusting this pagination.
                logger.warning("Repository %s returned a repeating cursor; retrying it per-repo", repo.full_name)
                active.discard(index)
                failed.append(repo)
            else:
                cursors[index] = next_cursor

    return records, failed


def fetch_repos_batched(
    client: GitHubClient,
    repos: list[RepositoryRecord],
    query_text: str,
    model_class: type,
    nodes_path: list[str],
    context_builder: Callable[[RepositoryRecord], dict],
    *,
    variables: dict | None = None,
    batch_size: int | None = None,
    stop_node: Callable[[dict], bool] | None = None,
) -> tuple[list, list[RepositoryRecord]]:
    """Fetch a repo-scoped resource for many repositories via aliased batches.

    Returns ``(records, failed_repos)`` — a failed batch marks all its repos as
    failed rather than raising, so the caller can retry them individually.
    ``stop_node`` ends a repository's pagination early when a node matches (for
    updated-at-ordered delta fetches).
    """
    shared_declarations, body, fragments = split_repo_query(query_text)
    size = batch_size or GITHUB_GRAPHQL_BATCH_SIZE

    records: list = []
    failed: list[RepositoryRecord] = []

    safe_repos = []
    for repo in repos:
        if _SAFE_NAME_RE.match(repo.owner) and _SAFE_NAME_RE.match(repo.name):
            safe_repos.append(repo)
        else:
            logger.warning("Repository %s has an unexpected name; fetching it individually", repo.full_name)
            failed.append(repo)

    for start in range(0, len(safe_repos), size):
        chunk = safe_repos[start : start + size]
        try:
            chunk_records, chunk_failed = _fetch_chunk(
                client,
                chunk,
                shared_declarations,
                body,
                fragments,
                model_class,
                nodes_path,
                context_builder,
                variables,
                stop_node,
            )
            records.extend(chunk_records)
            failed.extend(chunk_failed)
        except Exception:
            logger.exception(
                "Batched fetch failed for %d repos (%s...); they will be retried per-repo",
                len(chunk),
                chunk[0].full_name,
            )
            failed.extend(chunk)

    return records, failed


def fetch_org_records_batched(
    client: GitHubClient,
    org: str,
    *,
    query_text: str,
    model_class: type,
    nodes_path: list[str],
    per_repo: Callable[[RepositoryRecord], list],
    task_desc: str,
    max_workers: int,
    variables: dict | None = None,
    stop_node: Callable[[dict], bool] | None = None,
) -> list:
    """Org-wide batched fetch with a per-repo fallback for failed batches.

    Repos whose batch failed are retried individually through
    :func:`fetch_all_with_retry`; if any still fail, :class:`PartialOrgFetchError`
    is raised carrying *all* records that did arrive (batched + fallback), so the
    incremental store can merge them while holding the watermark.
    """
    all_repos = _common.fetch_org_repos_graphql(client, org)
    records, failed = fetch_repos_batched(
        client,
        all_repos,
        query_text,
        model_class,
        nodes_path,
        lambda repo: {"owner": repo.owner, "repo": repo.name},
        variables=variables,
        stop_node=stop_node,
    )
    if failed:
        logger.warning("Retrying %d repos individually after batched %s failures", len(failed), task_desc)
        try:
            records.extend(fetch_all_with_retry(failed, max_workers, per_repo, task_desc))
        except PartialOrgFetchError as exc:
            raise PartialOrgFetchError(records + exc.records, exc.failed_repos) from exc
    return records
