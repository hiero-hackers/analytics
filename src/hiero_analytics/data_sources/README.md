# GitHub Data Sources

This module provides the **GitHub ingestion layer** for the analytics pipeline.  
It handles API communication, pagination, normalization of GitHub objects, and optional caching.

The goal is to provide **clean, typed records** that downstream analytics code can use without worrying about GitHub API details.

---

## Overview

The data source layer is responsible for:

- Communicating with the GitHub REST and GraphQL APIs
- Handling authentication and rate limits
- Managing pagination
- Converting API responses into normalized Python models
- Supporting caching of API responses

The module exports a small public API for fetching repository, issue, and pull request data.

---

## Module Structure

```
data_sources/
│
├── cache.py
├── github_client.py
├── github_ingest.py
├── github_queries.py
├── github_search.py
├── models.py
└── pagination.py
```


---

## Public API

The following objects are exported through the package:

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

## Components

### GitHubClient

`github_client.py`

A low-level HTTP client for interacting with the GitHub API.

Features:
- Persistent HTTP connections via requests.Session
- Automatic authentication headers
- Rate-limit handling
- Support for REST and GraphQL requests


### GraphQL Ingestion

`github_ingest.py`

Provides higher-level functions that fetch and normalize GitHub data.

These functions automatically:
- handle GraphQL pagination
- convert API responses into typed records
- optionally fetch data across multiple repositories in parallel

### REST Search API

`github_search.py`

Supports GitHub's search endpoint.

### Data Models

GitHub objects are normalized into typed dataclasses.

e.g.
`RepositoryRecord`
`IssueRecord`
`PullRequestDifficultyRecord`

### Pagination Utilities

Provides reusable helpers for APIs that use pagination.

Used by REST endpoints:
```
paginate_page_number()
```

Used by GraphQL endpoints:
```
paginate_cursor()
```

### Caching

Location: `cache.py`

Provides simple file-based caching of API responses:
```
load_cache(key)
save_cache(key, data)
```

Cached responses are stored at:
```
.cache/github/
```

## Typical Workflow
A typical analytics pipeline will look like:
```
GitHub API
    ↓
GitHubClient
    ↓
github_ingest
    ↓
IssueRecord / RepositoryRecord / PullRequestDifficultyRecord
    ↓
transform → DataFrame
    ↓
metrics + charts
```
