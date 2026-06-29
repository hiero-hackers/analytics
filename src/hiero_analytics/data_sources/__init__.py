"""Public data-source helpers and models for the analytics package."""

from .github_client import GitHubClient
from .github_ingest import (
    fetch_issue_timeline_events_rest,
    fetch_org_contributor_activity_graphql,
    fetch_org_contributor_merged_pr_count_graphql,
    fetch_org_issues_graphql,
    fetch_org_merged_pr_difficulty_graphql,
    fetch_org_repos_graphql,
    fetch_repo_contributor_activity_graphql,
    fetch_repo_contributor_merged_pr_count_graphql,
    fetch_repo_issue_timeline_events_rest,
    fetch_repo_issues_graphql,
    fetch_repo_merged_pr_difficulty_graphql,
)
from .github_search import search_issues
from .models import (
    ContributorActivityRecord,
    ContributorMergedPRCountRecord,
    IssueRecord,
    IssueTimelineEventRecord,
    PullRequestDifficultyRecord,
    RepositoryRecord,
)
from .pagination import paginate_cursor

__all__ = [
    "GitHubClient",
    "search_issues",
    "fetch_org_issues_graphql",
    "fetch_org_repos_graphql",
    "fetch_org_merged_pr_difficulty_graphql",
    "fetch_org_contributor_activity_graphql",
    "fetch_org_contributor_merged_pr_count_graphql",
    "fetch_issue_timeline_events_rest",
    "fetch_repo_merged_pr_difficulty_graphql",
    "fetch_repo_contributor_activity_graphql",
    "fetch_repo_contributor_merged_pr_count_graphql",
    "fetch_repo_issue_timeline_events_rest",
    "fetch_repo_issues_graphql",
    "RepositoryRecord",
    "IssueRecord",
    "IssueTimelineEventRecord",
    "PullRequestDifficultyRecord",
    "ContributorActivityRecord",
    "ContributorMergedPRCountRecord",
    "paginate_cursor",
]
