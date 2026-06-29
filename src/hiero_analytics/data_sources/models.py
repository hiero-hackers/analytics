"""
Typed data models representing normalized GitHub records.

These dataclasses define the structured records produced by the GitHub
ingestion layer. They provide a consistent schema for repositories,
issues, and merged pull request difficulty metrics.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


def _parse_dt(value: str | None) -> datetime | None:
    """Parse an ISO datetime string from GitHub GraphQL response."""
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _extract_login(container: Mapping | None, key: str = "author") -> str | None:
    """Extract a user login (``container[key]["login"]``) defensively.

    Returns ``None`` when the key is missing, the actor node is malformed (GitHub can
    return a null actor, e.g. a deleted user), or the login is the dependabot bot.
    """
    actor = container.get(key) if isinstance(container, Mapping) else None
    login = actor.get("login") if isinstance(actor, Mapping) else None
    if not isinstance(login, str) or login in {"dependabot", "dependabot[bot]", "dependabot-preview[bot]"}:
        return None
    return login


def _extract_labels(container: Mapping | None, *, lower: bool = False) -> list[str]:
    """Extract label names from ``container["labels"]["nodes"]``."""
    if not isinstance(container, Mapping):
        return []
    labels = container.get("labels")
    nodes = labels.get("nodes", []) if isinstance(labels, Mapping) else []
    names = (n.get("name") for n in nodes if isinstance(n, Mapping))
    return [name.lower() if lower else name for name in names if isinstance(name, str)]


def _extract_label_name(container: Mapping | None) -> str | None:
    """Extract one lower-cased label name from ``container["label"]["name"]``."""
    label_node = container.get("label") if isinstance(container, Mapping) else None
    raw = label_node.get("name") if isinstance(label_node, Mapping) else None
    return raw.lower() if isinstance(raw, str) else None


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

    @staticmethod
    def _login(payload: dict | None) -> str | None:
        """Extract a login from a payload and filter out dependabot."""
        if not payload:
            return None
        login = payload.get("login")
        if login == "dependabot":
            return None
        return login

@dataclass(frozen=True)
class RepositoryRecord(BaseRecord):
    """Metadata describing a GitHub repository."""
    full_name: str
    name: str
    owner: str
    created_at: datetime | None = None
    stargazers: int | None = None
    forks: int | None = None
    pushed_at: datetime | None = None
    language: str | None = None

    @classmethod
    def from_github_node(cls, node: dict, context: dict) -> list[RepositoryRecord]:
        """Hydrate repository records from a GraphQL repository node."""
        # Null-safe extraction of primaryLanguage name
        language = None
        if node.get("primaryLanguage") and isinstance(node["primaryLanguage"], Mapping):
            language = node["primaryLanguage"].get("name")
        
        return [
            cls(
                full_name=f"{cls._owner(context)}/{node['name']}",
                name=node["name"],
                owner=cls._owner(context),
                created_at=_parse_dt(node.get("createdAt")),
                stargazers=node.get("stargazerCount"),
                forks=node.get("forkCount"),
                pushed_at=_parse_dt(node.get("pushedAt")),
                language=language,
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
    updated_at: datetime | None = None

    @classmethod
    def from_github_node(cls, node: dict, context: dict) -> list[IssueRecord]:
        """Hydrate issue records from a GraphQL issue node."""
        repo_name = cls._repo_name(context)
        labels = _extract_labels(node, lower=True)
        return [
            cls(
                repo=repo_name,
                number=node["number"],
                title=node["title"],
                state=node["state"],
                created_at=_parse_dt(node["createdAt"]),
                closed_at=_parse_dt(node.get("closedAt")),
                labels=labels,
                updated_at=_parse_dt(node.get("updatedAt")),
            )
        ]


@dataclass(frozen=True)
class IssueTimelineEventRecord:
    """A normalized issue timeline event used for historical state reconstruction."""

    repo: str
    issue_number: int
    event_type: str
    occurred_at: datetime
    label: str | None = None

    @classmethod
    def from_timeline_item(cls, node: dict, context: dict) -> list[IssueTimelineEventRecord]:
        """Hydrate a normalized timeline event from a GraphQL timeline node."""
        typename = str(node.get("__typename", "")).lower()
        event_type_map = {
            "labeledevent": "labeled",
            "unlabeledevent": "unlabeled",
            "closedevent": "closed",
            "reopenedevent": "reopened",
        }

        event_type = event_type_map.get(typename)
        if event_type is None:
            return []

        occurred_at = _parse_dt(node.get("createdAt"))
        if occurred_at is None:
            return []

        since = context.get("since")
        if isinstance(since, datetime) and occurred_at < since:
            return []

        label_name: str | None = None
        label_node = node.get("label")
        if isinstance(label_node, Mapping):
            raw_label = label_node.get("name")
            if isinstance(raw_label, str):
                label_name = raw_label.lower()

        owner = str(context.get("owner", ""))
        repo = str(context.get("repo", ""))
        repo_name = f"{owner}/{repo}" if owner and repo else ""

        return [
            cls(
                repo=repo_name,
                issue_number=int(context.get("issue_number", 0)),
                event_type=event_type,
                occurred_at=occurred_at,
                label=label_name,
            )
        ]

    @classmethod
    def from_rest_event(
        cls,
        event: dict,
        *,
        owner: str,
        repo: str,
        issue_number: int,
    ) -> IssueTimelineEventRecord | None:
        """Hydrate a normalized timeline event from the REST timeline endpoint."""
        event_type = str(event.get("event", "")).lower()

        if event_type not in {"labeled", "unlabeled", "closed", "reopened"}:
            return None

        occurred_at = _parse_dt(event.get("created_at"))
        if occurred_at is None:
            return None

        label_name = (
            _extract_label_name(event)
            if event_type in {"labeled", "unlabeled"}
            else None
        )

        return cls(
            repo=f"{owner}/{repo}",
            issue_number=issue_number,
            event_type=event_type,
            occurred_at=occurred_at,
            label=label_name,
        )

    @classmethod
    def from_github_node(cls, node: dict, context: dict) -> list[IssueTimelineEventRecord]:
        """Hydrate label add/remove events from a GraphQL issue node's timelineItems.

        Each issue node carries a ``timelineItems`` connection filtered to
        ``LABELED_EVENT``/``UNLABELED_EVENT``; this expands it into one record
        per event, matching the normalization of :meth:`from_rest_event`
        (lower-cased event type and label name).
        """
        full_repo = BaseRecord._repo_name(context)

        issue_number = node.get("number")
        if not isinstance(issue_number, int):
            return []

        type_map = {"LabeledEvent": "labeled", "UnlabeledEvent": "unlabeled"}
        records: list[IssueTimelineEventRecord] = []

        timeline = node.get("timelineItems", {})
        if timeline.get("pageInfo", {}).get("hasNextPage"):
            # The fragment caps timelineItems at 100 and does not paginate the
            # inner connection. Surface when an issue actually exceeds that so we
            # know whether nested pagination is worth building.
            logger.warning(
                "Issue %s#%s has >100 label events; only the first 100 were "
                "fetched (label-event history truncated for this issue)",
                full_repo, issue_number,
            )

        for item in timeline.get("nodes", []):
            if not isinstance(item, Mapping):
                continue

            event_type = type_map.get(item.get("__typename"))
            if event_type is None:
                continue

            occurred_at = _parse_dt(item.get("createdAt"))
            if occurred_at is None:
                continue

            label_name = _extract_label_name(item)

            records.append(
                cls(
                    repo=full_repo,
                    issue_number=issue_number,
                    event_type=event_type,
                    occurred_at=occurred_at,
                    label=label_name,
                )
            )

        return records


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
        """Hydrate pull-request difficulty records from a GraphQL PR node."""
        repo_name = cls._repo_name(context)
        # Author is optional metadata here — a PR with no author still yields its
        # difficulty/label records (difficulty is about the linked issues, not the actor).
        author = _extract_login(node)
        issues = node.get("closingIssuesReferences", {}).get("nodes", [])
        records = []
        for issue in issues:
            labels = _extract_labels(issue)
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
        records = []
        activity_source = context.get("activity_source", "pull_request")
        pr_author = _extract_login(node)

        if activity_source == "issue":
            issue_number = node["number"]
            issue_author = pr_author
            issue_created_at = _parse_dt(node.get("createdAt"))
            if issue_created_at and (cutoff is None or issue_created_at >= cutoff) and issue_author:
                records.append(
                    cls(
                        repo=repo_name,
                        activity_type="authored_issue",
                        actor=issue_author,
                        occurred_at=issue_created_at,
                        target_type="issue",
                        target_number=issue_number,
                        target_author=issue_author,
                    )
                )
            return records

        pr_number = node["number"]
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
            review_author = _extract_login(review)
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
        merged_by = _extract_login(node, "mergedBy")
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
        """Hydrate merged-PR count records from a GraphQL search node."""
        repo_name = cls._repo_name(context)
        login = cls._login({"login": context.get("login", "")})
        if not login:
            return []
        return [
            cls(
                repo=repo_name,
                login=login,
                merged_pr_count=node.get("issueCount", 0),
            )
        ]


@dataclass(frozen=True)
class ScorecardRecord:
    """Normalized OpenSSF Scorecard record."""
    repo: str
    score: float
    checks: dict[str, int]
    date: datetime

@dataclass(frozen=True)
class CodeOwnersRecord:
    """Represents the presence of a CODEOWNERS file in a repository."""
    repo: str
    status: bool

@dataclass(frozen=True)
class RunnerRecord:
    """Represents usage for a specific GitHub Actions job."""
    repo: str
    workflow_file: str
    job_name: str
    runner: str
    is_self_hosted: bool | None # None = undefine/fallback/env-param
