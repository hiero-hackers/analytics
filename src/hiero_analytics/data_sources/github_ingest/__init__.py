"""GitHub data ingestion utilities using the GraphQL API.

This package provides functions for retrieving repositories, issues, and merged
pull request metadata from GitHub. Data is fetched using cursor-based pagination
and can be aggregated across an organization with parallel requests.

The implementation is split by resource for readability:

- ``_common``       — generic paginated/parallel fetch engine + repo listing
- ``issues``        — issue and issue-label-event ingestion (GraphQL)
- ``timeline``      — issue timeline / events ingestion (REST)
- ``pull_requests`` — merged-PR difficulty ingestion (GraphQL)
- ``contributors``  — contributor activity + merged-PR-count ingestion (GraphQL)

This module is a thin facade that re-exports the public API, so existing
``from ...github_ingest import X`` imports keep working unchanged. Tests that
monkeypatch an internal helper must patch it on the *owning submodule*
(``github_ingest.issues``, ``.contributors``, ``._common``, ``.timeline``),
because that is where the call site resolves the name.
"""

from __future__ import annotations

from ._common import (
    _fetch_org_records_parallel as _fetch_org_records_parallel,
)
from ._common import (
    fetch_github_resource,
    fetch_org_repos_graphql,
    fetch_org_resource_parallel,
)
from .contributors import (
    _fetch_repo_contributor_activity_at_cutoff as _fetch_repo_contributor_activity_at_cutoff,
)
from .contributors import (
    _fetch_repo_issue_activity_graphql as _fetch_repo_issue_activity_graphql,
)
from .contributors import (
    _fetch_repo_pull_request_activity_graphql as _fetch_repo_pull_request_activity_graphql,
)
from .contributors import (
    fetch_org_contributor_activity_graphql,
    fetch_org_contributor_merged_pr_count_graphql,
    fetch_repo_contributor_activity_graphql,
    fetch_repo_contributor_merged_pr_count_graphql,
)
from .issues import (
    fetch_org_issue_label_events_graphql,
    fetch_org_issues_graphql,
    fetch_repo_issue_label_events_graphql,
    fetch_repo_issue_label_events_since_graphql,
    fetch_repo_issues_graphql,
    fetch_repo_issues_since_graphql,
)
from .pull_requests import (
    fetch_org_merged_pr_difficulty_graphql,
    fetch_repo_merged_pr_difficulty_graphql,
)
from .timeline import (
    fetch_issue_timeline_events_rest,
    fetch_repo_issue_events_for_issues_since,
    fetch_repo_issue_events_rest_since,
    fetch_repo_issue_timeline_events_rest,
)

__all__ = [
    # generic engine + repos
    "fetch_github_resource",
    "fetch_org_resource_parallel",
    "fetch_org_repos_graphql",
    # issues
    "fetch_repo_issues_graphql",
    "fetch_repo_issues_since_graphql",
    "fetch_org_issues_graphql",
    "fetch_repo_issue_label_events_graphql",
    "fetch_repo_issue_label_events_since_graphql",
    "fetch_org_issue_label_events_graphql",
    # timeline / events (REST)
    "fetch_repo_issue_timeline_events_rest",
    "fetch_issue_timeline_events_rest",
    "fetch_repo_issue_events_rest_since",
    "fetch_repo_issue_events_for_issues_since",
    # merged PR difficulty
    "fetch_repo_merged_pr_difficulty_graphql",
    "fetch_org_merged_pr_difficulty_graphql",
    # contributor activity + merged PR count
    "fetch_repo_contributor_activity_graphql",
    "fetch_org_contributor_activity_graphql",
    "fetch_repo_contributor_merged_pr_count_graphql",
    "fetch_org_contributor_merged_pr_count_graphql",
]
