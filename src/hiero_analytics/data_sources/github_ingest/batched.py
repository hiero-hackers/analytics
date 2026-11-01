"""Batched multi-repo GraphQL fetching via repository field aliases.

Instead of one query per repository, several repositories are combined into a
single request::

    query BatchedRepos($c0: String, $c1: String, $states: [IssueState!]) {
      r0: repository(owner: "org", name: "repo-a") { issues(after: $c0, ...) {...} }
      r1: repository(owner: "org", name: "repo-b") { issues(after: $c1, ...) {...} }
      rateLimit { ... }
    }

Each alias keeps its own cursor, so repositories page independently and drop
out as they complete. The rate-limit point cost is roughly the sum of the
individual queries, but round-trips collapse from one-per-repo-page to
one-per-round — the dominant wall-clock win for org-wide fetches.

Repositories wait in a queue and each round carries up to ``width`` of them; a
repository that completes frees its slot for the next. A failure costs only the
affected aliases' current page:

- GitHub reports a GraphQL error per field, and ``errors[].path[0]`` names the
  alias, so the aliases without an error are kept and advance as usual.
- A query that was too big (``RESOURCE_LIMITS_EXCEEDED`` and kin, or a 502)
  halves the page size and the round width, and the affected aliases retry from
  the cursor they were on. Only at both floors does a repository fail.
- A repository that fails after fetching pages is retried once more, from its
  last good cursor, at the end of the queue. Restarting it from page 1 would
  re-spend those pages and most likely fail at the same place.

The single-repo ``queries/*.graphql`` files stay the source of truth: the
repository sub-selection is extracted from them here, so the batched and
per-repo paths can never drift apart.
"""

from __future__ import annotations

import logging
import re
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from hiero_analytics.config.github import GITHUB_GRAPHQL_BATCH_SIZE, GITHUB_GRAPHQL_MAX_PAGES

from ..dataset_store import PartialOrgFetchError
from ..github_client import GitHubClient, GitHubServerError
from ..models import RepositoryRecord
from ..pagination import PageSizePolicy, cursor_advances
from ..rate_limit import GraphQLResponseError, is_resource_limit_error
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


@dataclass(eq=False)
class _RepoProgress:
    """One repository's place in a batched fetch, kept across rounds.

    ``cursor`` is the last good cursor: the next request for this repository
    sends it, so every retry resumes there rather than at page 1. ``seen``
    holds every cursor sent, so a cursor that cycles back is caught.
    """

    index: int
    repo: RepositoryRecord
    cursor: str | None = None
    seen: set[str] = field(default_factory=set)
    records: list = field(default_factory=list)
    pages: int = 0
    resumed: bool = False

    @property
    def alias(self) -> str:
        """The field alias this repository is queried under."""
        return f"r{self.index}"


@dataclass
class _BatchOutcome:
    """Where each repository of a batched fetch ended up."""

    complete: list[_RepoProgress] = field(default_factory=list)
    failed: list[_RepoProgress] = field(default_factory=list)


def _records_of(progresses: list[_RepoProgress]) -> list:
    """The records of ``progresses``, grouped by repository in input order."""
    return [record for progress in sorted(progresses, key=lambda p: p.index) for record in progress.records]


def _describe_errors(errors: list[dict]) -> str:
    """Compact, de-duplicated label for a list of GraphQL error objects."""
    return ", ".join(sorted({str(error.get("type") or error.get("message") or "unknown") for error in errors}))


def _split_errors(errors: list[dict], aliases: set[str]) -> tuple[dict[str, list[dict]], list[dict]]:
    """Group GraphQL errors by the alias their ``path`` starts with; the rest concern the whole round."""
    by_alias: dict[str, list[dict]] = {}
    unattributed: list[dict] = []
    for error in errors:
        path = error.get("path")
        head = path[0] if isinstance(path, list) and path else None
        if isinstance(head, str) and head in aliases:
            by_alias.setdefault(head, []).append(error)
        else:
            unattributed.append(error)
    return by_alias, unattributed


def _shrink(page_size: PageSizePolicy, width: PageSizePolicy, reason: str) -> bool:
    """Halve the page size and the round width together; False once both are at their floors."""
    shrank_page = page_size.shrink(reason)
    shrank_width = width.shrink(reason)
    return shrank_page or shrank_width


def _page_repos(
    client: GitHubClient,
    pending: list[_RepoProgress],
    shared_declarations: list[str],
    body: str,
    fragments: str,
    model_class: type,
    nodes_path: list[str],
    context_builder: Callable[[RepositoryRecord], dict],
    variables: dict | None,
    stop_node: Callable[[dict], bool] | None,
    batch_size: int,
) -> _BatchOutcome:
    """Page every repository in ``pending`` to completion through aliased rounds.

    See the module docstring for how each kind of failure is handled. A
    repository ends in ``complete`` or in ``failed``; a failed one keeps the
    records and cursor it had reached.
    """
    outcome = _BatchOutcome()
    queue = deque(pending)
    active: list[_RepoProgress] = []
    page_size = PageSizePolicy()
    width = PageSizePolicy(batch_size, 1, label="GraphQL batch width")

    def fail(progress: _RepoProgress, reason: str, *, resumable: bool = True) -> None:
        """Give up on ``progress`` for now: requeue it once if it had made progress, else fail it."""
        if resumable and progress.pages and not progress.resumed:
            progress.resumed = True
            logger.warning(
                "Repository %s %s after %d page(s); retrying it from its last good cursor later",
                progress.repo.full_name,
                reason,
                progress.pages,
            )
            queue.append(progress)
            return
        logger.warning("Repository %s %s; leaving it to the caller", progress.repo.full_name, reason)
        outcome.failed.append(progress)

    def fail_round(reason: str) -> None:
        nonlocal active
        for progress in active:
            fail(progress, reason)
        active = []

    while queue or active:
        while len(active) > width.current:
            queue.appendleft(active.pop())
        while queue and len(active) < width.current:
            active.append(queue.popleft())

        query = _build_round_query(shared_declarations, body, fragments, [(p.index, p.repo) for p in active])
        round_variables = dict(variables or {})
        round_variables.update({f"c{p.index}": p.cursor for p in active})
        round_variables["pageSize"] = page_size.current

        errors_by_alias: dict[str, list[dict]] = {}
        try:
            response = client.graphql(query, round_variables)
        except GitHubServerError:
            # No data at all, so every alias re-sends its cursor in a smaller round.
            if not _shrink(page_size, width, "GitHub server error"):
                fail_round("kept failing with GitHub server errors at the smallest page and batch")
            continue
        except GraphQLResponseError as exc:
            response = exc.response
            errors_by_alias, unattributed = _split_errors(exc.errors, {p.alias for p in active})
            if unattributed or not errors_by_alias:
                # Not tied to one alias (MAX_NODE_LIMIT_EXCEEDED rejects the whole
                # query before it runs), so no alias's data from this round is trusted.
                oversized = bool(unattributed) and all(is_resource_limit_error(error) for error in unattributed)
                if not (oversized and _shrink(page_size, width, "GraphQL query too large")):
                    fail_round(f"failed with GraphQL errors ({_describe_errors(unattributed)})")
                continue
            logger.warning(
                "GraphQL errors for %d of %d repositories in a batched round (%s); keeping the others",
                len(errors_by_alias),
                len(active),
                _describe_errors([error for errors in errors_by_alias.values() for error in errors]),
            )
        except Exception:
            logger.exception("Batched round failed for %d repos (%s...)", len(active), active[0].repo.full_name)
            fail_round("failed in a batched round")
            continue

        payload = response.get("data")
        if not isinstance(payload, dict):
            payload = {}
        too_big: list[_RepoProgress] = []
        still_active: list[_RepoProgress] = []
        for progress in active:
            alias_errors = errors_by_alias.get(progress.alias)
            if alias_errors:
                if any(is_resource_limit_error(error) for error in alias_errors):
                    too_big.append(progress)
                else:
                    fail(progress, f"failed with GraphQL errors ({_describe_errors(alias_errors)})")
                continue

            container: object = payload.get(progress.alias)
            for key in nodes_path:
                container = container.get(key) if isinstance(container, dict) else None
            if not isinstance(container, dict):
                fail(progress, "is missing from the batched response")
                continue

            nodes = [node for node in (container.get("nodes") or []) if isinstance(node, dict)]
            page_info = container.get("pageInfo")
            if not isinstance(page_info, dict):
                page_info = {}
            next_cursor = page_info.get("endCursor")
            try:
                reached_stop = stop_node is not None and any(stop_node(node) for node in nodes)
                context = context_builder(progress.repo)
                page_records = [record for node in nodes for record in model_class.from_github_node(node, context)]
            except Exception:
                # One repository's unparseable page must not sink the others.
                logger.exception("Could not read a page of %s from the batched response", progress.repo.full_name)
                fail(progress, "returned a page that could not be read")
                continue
            finished = not page_info.get("hasNextPage") or reached_stop
            if not finished and not cursor_advances(progress.seen, next_cursor):
                # A claimed next page with no cursor, or one already sent, would
                # either loop or silently truncate. Drop this page: the retry
                # re-sends the cursor it came from.
                fail(progress, f"returned a missing or repeating cursor ({next_cursor!r})")
                continue

            progress.records.extend(page_records)
            progress.pages += 1
            if finished:
                outcome.complete.append(progress)
            elif progress.pages >= GITHUB_GRAPHQL_MAX_PAGES:
                fail(progress, f"exceeded {GITHUB_GRAPHQL_MAX_PAGES} pages (GITHUB_GRAPHQL_MAX_PAGES)", resumable=False)
            else:
                progress.seen.add(next_cursor)
                progress.cursor = next_cursor
                still_active.append(progress)

        if too_big:
            if _shrink(page_size, width, "GraphQL resource limits exceeded"):
                # First in line, so a narrower round still carries them next.
                still_active = too_big + still_active
            else:
                for progress in too_big:
                    fail(progress, "kept exceeding GraphQL resource limits at the smallest page and batch")
        elif not errors_by_alias:
            page_size.record_success()
            width.record_success()
        active = still_active

    return outcome


def _fetch_batched_progress(
    client: GitHubClient,
    repos: list[RepositoryRecord],
    query_text: str,
    model_class: type,
    nodes_path: list[str],
    context_builder: Callable[[RepositoryRecord], dict],
    *,
    variables: dict | None,
    batch_size: int | None,
    stop_node: Callable[[dict], bool] | None,
) -> _BatchOutcome:
    """Run the batched engine over ``repos``; unsafe names fail without a request."""
    shared_declarations, body, fragments = split_repo_query(query_text)
    pending: list[_RepoProgress] = []
    unsafe: list[_RepoProgress] = []
    for index, repo in enumerate(repos):
        progress = _RepoProgress(index, repo)
        if _SAFE_NAME_RE.match(repo.owner) and _SAFE_NAME_RE.match(repo.name):
            pending.append(progress)
        else:
            logger.warning("Repository %s has an unexpected name; fetching it individually", repo.full_name)
            unsafe.append(progress)

    outcome = _page_repos(
        client,
        pending,
        shared_declarations,
        body,
        fragments,
        model_class,
        nodes_path,
        context_builder,
        variables,
        stop_node,
        batch_size or GITHUB_GRAPHQL_BATCH_SIZE,
    )
    outcome.failed = unsafe + outcome.failed
    return outcome


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

    Returns ``(records, failed_repos)`` rather than raising, so the caller can
    retry the failed repositories individually. ``records`` covers exactly the
    repositories *not* in ``failed_repos``: a repository that failed partway is
    returned without the pages it did fetch, because a caller that retries it
    from scratch must not see those pages twice (and must not cache them as the
    whole repository). ``stop_node`` ends a repository's pagination early when
    a node matches (for updated-at-ordered delta fetches). ``batch_size`` is
    the starting round width (default ``GITHUB_GRAPHQL_BATCH_SIZE``).
    """
    outcome = _fetch_batched_progress(
        client,
        repos,
        query_text,
        model_class,
        nodes_path,
        context_builder,
        variables=variables,
        batch_size=batch_size,
        stop_node=stop_node,
    )
    return _records_of(outcome.complete), [progress.repo for progress in outcome.failed]


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
    repos: list[RepositoryRecord] | None = None,
) -> list:
    """Org-wide batched fetch with a per-repo fallback for repos the batch never started.

    A repository the batch could not fetch a single page of is retried
    individually through :func:`fetch_all_with_retry` (a restart from page 1
    costs nothing there). A repository that failed *partway*, even after its
    resume from the last good cursor, is not restarted: the fallback would
    re-spend its pages and most likely fail at the same place. Its pages are
    kept and it is reported incomplete.

    If any repository is incomplete or still failing, :class:`PartialOrgFetchError`
    is raised carrying *all* records that did arrive, so the incremental store
    can merge them while holding the watermark.

    ``repos`` limits the fetch to those repositories (the dataset store plans
    full and delta fetches per repository); by default the whole org is listed.
    """
    all_repos = repos if repos is not None else _common.fetch_org_repos_graphql(client, org)
    outcome = _fetch_batched_progress(
        client,
        all_repos,
        query_text,
        model_class,
        nodes_path,
        lambda repo: {"owner": repo.owner, "repo": repo.name},
        variables=variables,
        batch_size=None,
        stop_node=stop_node,
    )
    incomplete = [progress for progress in outcome.failed if progress.pages]
    untouched = [progress.repo for progress in outcome.failed if not progress.pages]
    records = _records_of(outcome.complete) + _records_of(incomplete)
    still_failing = [progress.repo for progress in incomplete]
    if incomplete:
        logger.error(
            "Batched %s stopped partway for: %s (keeping the pages that arrived)",
            task_desc,
            ", ".join(progress.repo.full_name for progress in incomplete),
        )
    if untouched:
        logger.warning("Retrying %d repos individually after batched %s failures", len(untouched), task_desc)
        try:
            records.extend(fetch_all_with_retry(untouched, max_workers, per_repo, task_desc))
        except PartialOrgFetchError as exc:
            records.extend(exc.records)
            still_failing.extend(exc.failed_repos)
    if still_failing:
        raise PartialOrgFetchError(records, still_failing)
    return records
