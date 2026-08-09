"""GitHub GraphQL ingestion utilities.

Resource-specific implementations live in separate modules:

- `_common` — shared pagination, parallel fetching, and repo listing
- `batched` — batched multi-repo GraphQL fetching
- `issues` — issue and label-event ingestion
- `pull_requests` — merged-PR difficulty ingestion
- `contributors` — contributor activity ingestion
- `hip_references` — HIP mention and spec inventory ingestion
- `releases` — GitHub Releases ingestion

This module re-exports the public API for backwards-compatible imports.
Internal helpers should be monkeypatched on their owning submodule.
"""

from __future__ import annotations

from ._common import (
    fetch_github_resource,
    fetch_org_repos_graphql,
    fetch_org_resource_parallel,
)
from .contributors import (
    CONTRIBUTOR_ACTIVITY_RESOURCE,
    fetch_org_contributor_activity_graphql,
    fetch_repo_contributor_activity_graphql,
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
from .hip_references import (
    PR_HIP_REFS_RESOURCE,
    fetch_hip_inventory,
    fetch_org_pr_hip_refs_graphql,
)
from .incremental import OrgIncrementalResource
from .issues import (
    ISSUE_LABEL_EVENTS_RESOURCE,
    ISSUES_RESOURCE,
    fetch_org_issue_label_events_graphql,
    fetch_org_issues_graphql,
    fetch_repo_issue_label_events_graphql,
    fetch_repo_issue_label_events_since_graphql,
    fetch_repo_issues_graphql,
    fetch_repo_issues_since_graphql,
)
from .pull_requests import (
    MERGED_PR_RESOURCE,
    fetch_org_merged_pr_difficulty_graphql,
    fetch_repo_merged_pr_difficulty_graphql,
)
from .releases import (
    RELEASES_RESOURCE,
    fetch_org_releases_graphql,
    fetch_repo_releases_graphql,
)

# Every org-wide incrementally fetched resource, by dataset name — the
# declarative registry the individual fetchers are built from.
ORG_INCREMENTAL_RESOURCES: dict[str, OrgIncrementalResource] = {
    resource.name: resource
    for resource in (
        ISSUES_RESOURCE,
        ISSUE_LABEL_EVENTS_RESOURCE,
        MERGED_PR_RESOURCE,
        CONTRIBUTOR_ACTIVITY_RESOURCE,
        PR_HIP_REFS_RESOURCE,
    )
}

__all__ = [
    # resource declarations
    "OrgIncrementalResource",
    "ORG_INCREMENTAL_RESOURCES",
    "ISSUES_RESOURCE",
    "ISSUE_LABEL_EVENTS_RESOURCE",
    "MERGED_PR_RESOURCE",
    "CONTRIBUTOR_ACTIVITY_RESOURCE",
    "PR_HIP_REFS_RESOURCE",
    "RELEASES_RESOURCE",
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
    # merged PR difficulty
    "fetch_repo_merged_pr_difficulty_graphql",
    "fetch_org_merged_pr_difficulty_graphql",
    # contributor activity + merged PR count
    "fetch_repo_contributor_activity_graphql",
    "fetch_org_contributor_activity_graphql",
    # HIP references + inventory
    "fetch_org_pr_hip_refs_graphql",
    "fetch_hip_inventory",
    # releases
    "fetch_repo_releases_graphql",
    "fetch_org_releases_graphql",
]
