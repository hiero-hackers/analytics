"""
Typed data models representing normalized GitHub records.

These dataclasses define the structured records produced by the GitHub
ingestion layer. They provide a consistent schema for repositories,
issues, and merged pull request difficulty metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


def _parse_dt(value: str | None) -> datetime | None:
    """Parse an ISO datetime string from GitHub GraphQL response."""
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class BaseRecord:
    """Base class for all GitHub data records."""
    @staticmethod
    def _owner(context: dict) -> str:
        """Extract the owner name from a GraphQL hydration context."""
        return context.get("owner", "")

    @staticmethod
    def _repo_name(context: dict) -> str:
        """Build an owner/repo name from a GraphQL hydration context."""
        owner = BaseRecord._owner(context)
        repo = context.get("repo", "")
        return f"{owner}/{repo}" if owner and repo else ""

    @classmethod
    def from_github_node(cls, node: dict, context: dict) -> list[BaseRecord]:
        """Hydrate appropriate model(s) from a GitHub GraphQL node."""
        raise NotImplementedError(f"Mapping not implemented for {cls.__name__}")


@dataclass(frozen=True)
class RepositoryRecord(BaseRecord):
    """Metadata describing a GitHub repository."""
    full_name: str
    name: str
    owner: str
    created_at: datetime | None = None
    stargazers: int | None = None
    forks: int | None = None

    @classmethod
    def from_github_node(cls, node: dict, context: dict) -> list[RepositoryRecord]:
        return [
            cls(
                full_name=f"{cls._owner(context)}/{node['name']}",
                name=node["name"],
                owner=cls._owner(context),
                created_at=_parse_dt(node.get("createdAt")),
                stargazers=node.get("stargazerCount"),
                forks=node.get("forkCount"),
            )
        ]


@dataclass(frozen=True)
class IssueRecord(BaseRecord):
    """A normalized GitHub issue record."""
    repo: str
    number: int
    title: str
    state: str
    created_at: datetime
    closed_at: datetime | None
    labels: list[str]

    @classmethod
    def from_github_node(cls, node: dict, context: dict) -> list[IssueRecord]:
        repo_name = cls._repo_name(context)
        labels = [label["name"].lower() for label in node.get("labels", {}).get("nodes", [])]
        return [
            cls(
                repo=repo_name,
                number=node["number"],
                title=node["title"],
                state=node["state"],
                created_at=_parse_dt(node["createdAt"]),
                closed_at=_parse_dt(node.get("closedAt")),
                labels=labels,
            )
        ]


@dataclass(frozen=True)
class PullRequestDifficultyRecord(BaseRecord):
    """Metadata linking a merged pull request to the issues it closes."""
    repo: str
    pr_number: int
    pr_created_at: datetime
    pr_merged_at: datetime
    pr_additions: int
    pr_deletions: int
    pr_changed_files: int
    issue_number: int
    issue_labels: list[str]
    author: str | None = None

    @classmethod
    def from_github_node(cls, node: dict, context: dict) -> list[PullRequestDifficultyRecord]:
        repo_name = cls._repo_name(context)
        author = node.get("author", {}).get("login")
        issues = node.get("closingIssuesReferences", {}).get("nodes", [])
        records = []
        for issue in issues:
            labels = [label["name"] for label in issue.get("labels", {}).get("nodes", [])]
            records.append(
                cls(
                    repo=repo_name,
                    pr_number=node["number"],
                    pr_created_at=_parse_dt(node["createdAt"]),
                    pr_merged_at=_parse_dt(node["mergedAt"]),
                    pr_additions=node["additions"],
                    pr_deletions=node["deletions"],
                    pr_changed_files=node["changedFiles"],
                    issue_number=issue["number"],
                    issue_labels=labels,
                    author=author,
                )
            )
        return records


@dataclass(frozen=True)
class ContributorActivityRecord(BaseRecord):
    """A normalized contributor activity event for issue/PR lifecycle actions."""
    repo: str
    activity_type: str
    actor: str
    occurred_at: datetime
    target_type: str
    target_number: int
    target_author: str | None = None
    detail: str | None = None
    author: str | None = None

    @classmethod
    def from_github_node(cls, node: dict, context: dict) -> list[ContributorActivityRecord]:
        repo_name = cls._repo_name(context)
        cutoff = context.get("cutoff")
        pr_number = node["number"]
        records = []
        
        pr_author = node.get("author", {}).get("login") if node.get("author") else None
        pr_created_at = _parse_dt(node.get("createdAt"))
        if pr_created_at and (cutoff is None or pr_created_at >= cutoff) and pr_author:
            records.append(
                cls(
                    repo=repo_name,
                    activity_type="authored_pull_request",
                    actor=pr_author,
                    occurred_at=pr_created_at,
                    target_type="pull_request",
                    target_number=pr_number,
                    target_author=pr_author,
                )
            )
            
        for review in node.get("reviews", {}).get("nodes", []):
            review_author = review.get("author", {}).get("login") if review.get("author") else None
            reviewed_at = _parse_dt(review.get("submittedAt"))
            if reviewed_at and (cutoff is None or reviewed_at >= cutoff) and review_author:
                records.append(
                    cls(
                        repo=repo_name,
                        activity_type="reviewed_pull_request",
                        actor=review_author,
                        occurred_at=reviewed_at,
                        target_type="pull_request",
                        target_number=pr_number,
                        target_author=pr_author,
                        detail=review.get("state"),
                    )
                )
                
        merged_at = _parse_dt(node.get("mergedAt"))
        merged_by = node.get("mergedBy", {}).get("login") if node.get("mergedBy") else None
        if merged_at and (cutoff is None or merged_at >= cutoff) and merged_by:
            records.append(
                cls(
                    repo=repo_name,
                    activity_type="merged_pull_request",
                    actor=merged_by,
                    occurred_at=merged_at,
                    target_type="pull_request",
                    target_number=pr_number,
                    target_author=pr_author,
                )
            )
        return records


@dataclass(frozen=True)
class ContributorMergedPRCountRecord(BaseRecord):
    """Total count of merged pull requests for a contributor in a repository."""
    repo: str
    login: str
    merged_pr_count: int

    @classmethod
    def from_github_node(cls, node: dict, context: dict) -> list[ContributorMergedPRCountRecord]:
        repo_name = cls._repo_name(context)
        login = context.get("login", "")
        return [
            cls(
                repo=repo_name,
                login=login,
                merged_pr_count=node.get("issueCount", 0),
            )
        ]
