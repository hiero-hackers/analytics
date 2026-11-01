# GitHub Data Sources

This module provides the **GitHub ingestion layer** for the analytics pipeline.
It handles API communication, pagination, normalization of GitHub objects, and parallel ingestion across repositories.

The goal is to expose a **small, stable API that returns typed records**, so downstream analytics code does not need to deal with GitHub API details.

---

# Overview

The data source layer is responsible for:

- Communicating with the **GitHub REST and GraphQL APIs**
- Handling **authentication and rate limits**
- Managing **cursor and page-based pagination**
- Converting API responses into **normalized Python dataclasses**
- Supporting **parallel repository ingestion**

The module exposes a **small public interface** for retrieving repositories, issues, and pull request metadata.

---

# Module Structure

```
data_sources/
│
├── github_client.py        # HTTP client with retry and rate limit handling
├── github_ingest/          # GraphQL ingestion + the org-incremental resource registry
├── github_rest.py          # REST helpers: CODEOWNERS presence, Actions-runner scanning
├── queries.py              # GraphQL query-document loading (queries/ *.graphql files)
├── dataset_store.py        # durable incremental datasets (watermarked, self-healing)
├── cache.py                # short-TTL cache for repeated within-day runs
├── serialization.py        # record <-> JSON round-tripping shared by both stores
├── models.py               # Typed data records
└── pagination.py           # Generic pagination helpers
```

---

# Public API

The package exposes the following primary interfaces:

```python
from hiero_analytics.data_sources import (
    GitHubClient,
    search_issues,
    fetch_org_issues_graphql,
    fetch_repo_issues_graphql,
    fetch_org_repos_graphql,
    fetch_repo_merged_pr_difficulty_graphql,
    fetch_org_merged_pr_difficulty_graphql,
    RepositoryRecord,
    IssueRecord,
    PullRequestDifficultyRecord,
)
```

---

# Components

## GitHubClient

`github_client.py`

A low-level HTTP client for interacting with the GitHub API.

Features:

- Persistent HTTP connections via `requests.Session`
- Automatic authentication using `GITHUB_TOKEN`
- Built-in retry logic
- REST and GraphQL support
- Rate limit awareness
- Usage tracking for monitoring API usage

Example:

```python
client = GitHubClient()

data = client.get("https://api.github.com/repos/owner/repo")
```

GraphQL example:

```python
data = client.graphql(query, variables)
```

---

# GraphQL Ingestion Layer

`github_ingest.py`

This module contains the higher-level ingestion functions that fetch and normalize GitHub data.

Responsibilities:

- Handle **GraphQL cursor pagination**
- Convert API responses into **typed records**
- Support **parallel ingestion across repositories**

Example:

```python
client = GitHubClient()

issues = fetch_org_issues_graphql(
    client,
    org="hiero-ledger",
)
```

These functions return **typed dataclasses**, not raw API responses.

---

# REST Helpers

`github_rest.py`

REST-backed checks that have no GraphQL equivalent: CODEOWNERS file presence
(`has_codeowners_file`) and per-job Actions-runner classification from workflow
YAML (`fetch_repo_workflows`). Workflow files are fetched through the shared
fan-out (`fetch_all_with_retry`), so transient failures retry once and a
persistently failing file raises rather than silently shrinking the scan.
Only a 404 ever reads as "not present" — other errors propagate.

---

# Data Models

`models.py`

GitHub objects are normalized into typed dataclasses.

### RepositoryRecord

```python
RepositoryRecord(
    full_name="org/repo",
    name="repo",
    owner="org",
)
```

### IssueRecord

```python
IssueRecord(
    repo="org/repo",
    number=123,
    title="Bug report",
    state="OPEN",
    created_at=datetime,
    closed_at=None,
    labels=["bug", "good-first-issue"],
)
```

### PullRequestDifficultyRecord

```python
PullRequestDifficultyRecord(
    repo="org/repo",
    pr_number=12,
    pr_created_at=datetime,
    pr_merged_at=datetime,
    pr_additions=120,
    pr_deletions=30,
    pr_changed_files=4,
    issue_number=88,
    issue_labels=["good-first-issue"],
)
```

---

# Pagination Utilities

`pagination.py`

Reusable helpers for APIs that use pagination.

### Page-number pagination (REST APIs)

```python
paginate_page_number(fetch_page)
```

Used by GitHub search endpoints.

### Cursor pagination (GraphQL APIs)

```python
paginate_cursor(fetch_page)  # fetch_page(cursor, page_size)
```

Used by GraphQL queries for repositories, issues, and pull requests. Queries take
the page size as a `$pageSize` variable; on a `GitHubServerError` (GitHub's 502/504
for a query that ran too long) the loop halves the page size and retries the same
cursor, then recovers after a few clean pages. When a page reports another page
but the cursor is missing or one already sent (a repeat or a cycle), that response
is discarded and the same page is retried once; a second stall raises
`CursorStalledError` instead of looping or returning a truncated result as
complete. Past `GITHUB_GRAPHQL_MAX_PAGES` (default 5,000) the loop raises
`PaginationLimitError`.

Both helpers provide:

- logging for long-running pagination loops
- a hard page cap, an optional soft `max_pages` cap that truncates on purpose,
  and a one-retry stall guard on cursor pagination
- automatic result aggregation

### Batched rounds (`github_ingest/batched.py`)

Org-wide fetches alias several repositories into one query. Repositories wait in
a queue, and each round carries up to `GITHUB_GRAPHQL_BATCH_SIZE` of them. A
GraphQL error in the response body names its alias in `errors[].path[0]`, so the
other aliases in that response are kept. A query that was too big
(`RESOURCE_LIMITS_EXCEEDED`, `MAX_NODE_LIMIT_EXCEEDED`, or a 502/504) halves both
the page size and the round width, and the affected repositories retry from the
cursor they were on. A repository that fails partway is retried once from its
last good cursor; only a repository that never fetched a page goes to the
per-repo fallback.

---

# Caching

GraphQL ingestion helpers support a small file-backed cache for normalized records.
This reduces repeated API fetches when multiple scripts use the same underlying data.

By default:

- cache is enabled
- cache files are written under `outputs/cache/github/`
- entries expire after 900 seconds

Environment variables:

```bash
GITHUB_CACHE_ENABLED=true
GITHUB_CACHE_TTL_SECONDS=900
```
Setting `GITHUB_CACHE_TTL_SECONDS` to `0` or a negative number disables
expiry entirely — entries are treated as fresh forever and only go away if
you clear `outputs/cache/github/` by hand. This is intentional (handy for
offline debugging), but easy to trigger by accident with an empty or
malformed value, so using it logs a warning rather than failing silently.

You can also override caching per call:

```python
issues = fetch_org_issues_graphql(
    client,
    org="hiero-ledger",
    cache_ttl_seconds=300,
)
```

Or force a refresh while still replacing the cached copy:

```python
issues = fetch_org_issues_graphql(
    client,
    org="hiero-ledger",
    refresh=True,
)
```

---

# Typical Workflow

A typical analytics ingestion pipeline looks like:

```
GitHub API
    ↓
GitHubClient
    ↓
github_ingest
    ↓
RepositoryRecord / IssueRecord / PullRequestDifficultyRecord
    ↓
transform → DataFrame
    ↓
metrics + charts
```

This design keeps **API logic isolated**, allowing analytics code to operate on clean, structured data.
