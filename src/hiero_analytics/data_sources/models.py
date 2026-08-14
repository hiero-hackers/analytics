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

from hiero_analytics.domain.bots import is_bot_login
from hiero_analytics.domain.hip_references import extract_hip_mentions

from .serialization import parse_github_datetime

logger = logging.getLogger(__name__)


def _parse_dt(value: str | None) -> datetime | None:
    """Parse an ISO datetime from a GraphQL node (strict: malformed raises)."""
    return parse_github_datetime(value, strict=True)


def _extract_login(container: Mapping | None, key: str = "author") -> str | None:
    """Extract a user login (``container[key]["login"]``) defensively.

    Returns ``None`` when the key is missing, the actor node is malformed (GitHub
    can return a null actor, e.g. a deleted user), or the login is an automation
    account per the canonical :func:`hiero_analytics.domain.bots.is_bot_login`
    policy — one bot filter for both ingestion and analysis.
    """
    actor = container.get(key) if isinstance(container, Mapping) else None
    login = actor.get("login") if isinstance(actor, Mapping) else None
    if not isinstance(login, str) or is_bot_login(login):
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
class IssueTimelineEventRecord(BaseRecord):
    """A normalized issue timeline event used for historical state reconstruction."""

    repo: str
    issue_number: int
    event_type: str
    occurred_at: datetime
    label: str | None = None
    actor: str | None = None

    @classmethod
    def from_github_node(cls, node: dict, context: dict) -> list[IssueTimelineEventRecord]:
        """Hydrate label add/remove events from a GraphQL issue node's timelineItems.

        Each issue node carries a ``timelineItems`` connection filtered to
        ``LABELED_EVENT``/``UNLABELED_EVENT``; this expands it into one record
        per event, matching the normalization of :meth:`from_rest_event`
        (lower-cased event type and label name).
        """
        full_repo = cls._repo_name(context)

        issue_number = node.get("number")
        if not isinstance(issue_number, int):
            return []

        type_map = {"LabeledEvent": "labeled", "UnlabeledEvent": "unlabeled"}
        records: list[IssueTimelineEventRecord] = []

        timeline = node.get("timelineItems") or {}
        if (timeline.get("pageInfo") or {}).get("hasNextPage"):
            # The fragment caps timelineItems at 100 and does not paginate the
            # inner connection. Surface when an issue actually exceeds that so we
            # know whether nested pagination is worth building.
            logger.warning(
                "Issue %s#%s has >100 label events; only the first 100 were "
                "fetched (label-event history truncated for this issue)",
                full_repo,
                issue_number,
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
                    actor=_extract_login(item, "actor"),
                )
            )

        return records


@dataclass(frozen=True)
class PullRequestDifficultyRecord(BaseRecord):
    """Metadata for a merged pull request and the issues it closes (if any).

    Every merged PR yields at least one record: one per linked closing issue, or
    a single record with ``issue_number`` None when nothing is linked — so the
    dataset covers all merged PRs, and per-contributor counts derived from it
    are not biased toward issue-linked work.
    """

    repo: str
    pr_number: int
    pr_created_at: datetime
    pr_merged_at: datetime
    pr_additions: int
    pr_deletions: int
    pr_changed_files: int
    issue_number: int | None
    issue_labels: list[str]
    author: str | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_github_node(cls, node: dict, context: dict) -> list[PullRequestDifficultyRecord]:
        """Hydrate pull-request difficulty records from a GraphQL PR node."""
        repo_name = cls._repo_name(context)
        # Author is optional metadata here — a PR with no author still yields its
        # difficulty/label records (difficulty is about the linked issues, not the actor).
        author = _extract_login(node)
        issues = (node.get("closingIssuesReferences") or {}).get("nodes") or []
        base = dict(
            repo=repo_name,
            pr_number=node["number"],
            pr_created_at=_parse_dt(node["createdAt"]),
            pr_merged_at=_parse_dt(node["mergedAt"]),
            pr_additions=node["additions"],
            pr_deletions=node["deletions"],
            pr_changed_files=node["changedFiles"],
            author=author,
            updated_at=_parse_dt(node.get("updatedAt")),
        )
        if not issues:
            return [cls(issue_number=None, issue_labels=[], **base)]
        return [cls(issue_number=issue["number"], issue_labels=_extract_labels(issue), **base) for issue in issues]


@dataclass(frozen=True)
class HipReferenceRecord(BaseRecord):
    """A HIP number a pull request mentions (or a no-mention marker).

    Every swept PR yields at least one record: one per distinct HIP number
    found in its title, branch name, or body — or a single record with ``hip``
    None when it mentions no HIP. The markers matter: they let the dataset's
    incremental watermark advance across *all* PRs (not just the rare
    HIP-citing ones), and they give analysis a per-repo denominator of PRs
    swept. PR body text is matched at hydration and never stored.
    """

    repo: str
    pr_number: int
    pr_title: str
    pr_state: str
    pr_created_at: datetime
    pr_merged_at: datetime | None
    hip: int | None
    match_sources: str  # "|"-joined subset of title/branch/body; "" for markers
    snippet: str
    # Distancing cue ("waiting on", "prepares for", ...) found before a
    # body-only mention — the mechanical false-positive signal. Analysis
    # excludes qualified references from counts but keeps them as evidence.
    qualifier: str = ""
    author: str | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_github_node(cls, node: dict, context: dict) -> list[HipReferenceRecord]:
        """Hydrate HIP-reference records from a GraphQL PR node."""
        title = node.get("title") or ""
        mentions = extract_hip_mentions(
            title=title,
            branch=node.get("headRefName") or "",
            body=node.get("body") or "",
        )
        base = dict(
            repo=cls._repo_name(context),
            pr_number=node["number"],
            pr_title=title[:200],
            pr_state=node.get("state") or "",
            pr_created_at=_parse_dt(node["createdAt"]),
            pr_merged_at=_parse_dt(node.get("mergedAt")),
            author=_extract_login(node),
            updated_at=_parse_dt(node.get("updatedAt")),
        )
        if not mentions:
            # Markers exist only to advance the watermark and give analysis a
            # swept-PR denominator; dropping the title/author keeps ~97% of the
            # persisted dataset (the PRs citing no HIP) small.
            return [cls(hip=None, match_sources="", snippet="", **{**base, "pr_title": "", "author": None})]
        return [
            cls(hip=m.number, match_sources="|".join(m.sources), snippet=m.snippet, qualifier=m.qualifier, **base)
            for m in mentions
        ]


@dataclass(frozen=True)
class HipSpecRecord(BaseRecord):
    """One HIP specification from the proposals repository's frontmatter.

    Hydrated from ``HIP/hip-<n>.md`` YAML frontmatter, not from a GraphQL
    node. Frontmatter dates are kept as the raw strings the spec authors
    wrote; ``updated_at`` carries the parsed best-effort timestamp so the
    dataset store has a watermark to advance.
    """

    number: int
    title: str
    status: str
    category: str
    hip_type: str
    created: str
    updated: str
    # HIP-1 requires a release number when a Standards Track spec goes Final.
    release: str = ""
    updated_at: datetime | None = None


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
        """Build ContributorActivityRecord instances from a raw GitHub GraphQL node."""
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

        for review in (node.get("reviews") or {}).get("nodes") or []:
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
class ScorecardRecord:
    """Normalized OpenSSF Scorecard record."""

    repo: str
    score: float
    checks: dict[str, int]
    date: datetime


@dataclass(frozen=True)
class DependencyManifestRecord:
    """One SBOM package entry for a repo, before org-repo resolution.

    ``package_name`` and ``ecosystem`` are parsed from the package URL
    (purl) in the SBOM's ``externalRefs``, not the raw SPDX ``name`` field —
    purl gives a consistent ecosystem+name split across npm/PyPI/Maven/
    Cargo/Go, where the raw name field's shape varies per ecosystem.
    """

    repo: str
    package_name: str
    ecosystem: str
    version: str | None


@dataclass(frozen=True)
class SbomCoverageRecord:
    """Per-repo SBOM fetch outcome — kept distinct from the package list itself.

    ``status`` is one of ``"ok"`` (SBOM available, packages parsed —
    ``package_count`` may still be 0 for a repo with a genuinely empty
    manifest), ``"disabled"`` (dependency graph off for this repo, or the
    endpoint 404/403'd), or ``"error"`` (fetch failed for a reason other
    than disablement; surfaced rather than silently dropped). This is what
    makes "no edges" distinguishable from "no data" downstream.
    """

    repo: str
    status: str
    package_count: int


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
    is_self_hosted: bool | None  # None = undefine/fallback/env-param
