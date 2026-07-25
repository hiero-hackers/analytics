"""HIP-implementation ingestion: PR HIP references and the HIP spec inventory.

Two datasets back the HIP-implementation pipeline:

- ``pr_hip_references`` — every merged/open PR org-wide *since the start of
  the Hiero era*, hydrated into one record per distinct HIP number it mentions
  (plus a no-mention marker per PR, so the incremental watermark advances over
  all swept PRs and analysis has a swept denominator). Incremental like the
  other org datasets, with every fetch floor-bounded at the era start via the
  ``UPDATED_AT``-descending early stop.
- ``hip_inventory`` — the canonical HIP list, parsed from the proposals
  repository's spec frontmatter. Tiny (one tree query), so every refresh is a
  full re-read merged through the same store.

Upsert-only caveats (both heal on the periodic full refresh): a mention edited
*out* of a PR leaves its old record behind, an OPEN PR closed without merging
keeps its last OPEN record, and a spec file deleted from the proposals repo
keeps its inventory row.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import yaml

from hiero_analytics.config.analysis import HIERO_ERA_START
from hiero_analytics.config.github import GITHUB_MAX_WORKERS, HIP_PROPOSALS_DIR, HIP_PROPOSALS_REPO
from hiero_analytics.config.paths import dataset_path
from hiero_analytics.data_sources.queries import load_query

from ..dataset_store import fetch_incremental
from ..github_client import GitHubClient
from ..models import HipReferenceRecord, HipSpecRecord
from ..pagination import extract_graphql_cursor_page, paginate_cursor
from ..serialization import parse_github_datetime
from ._common import node_older_than
from .batched import fetch_org_records_batched
from .incremental import OrgIncrementalResource, fetch_org_incremental

logger = logging.getLogger(__name__)

PR_HIP_REFS_RESOURCE = OrgIncrementalResource(
    name="pr_hip_references",
    model_class=HipReferenceRecord,
    key_of=lambda record: (record.repo, record.pr_number, record.hip),
    updated_at_of=lambda record: record.updated_at,
    task_desc="PR HIP references",
)


def fetch_repo_pr_hip_refs_since_graphql(
    client: GitHubClient,
    owner: str,
    repo: str,
    since: datetime,
) -> list[HipReferenceRecord]:
    """Fetch HIP-reference records for PRs updated at/after ``since``.

    Same delta style as the merged-PR dataset: no ``filterBy: since`` exists
    for ``pullRequests``, so pagination (ordered ``UPDATED_AT`` descending)
    stops at the first page containing an older PR. Boundary-page re-sends are
    harmless — the incremental merge is an idempotent upsert.
    """
    query = load_query("pr_hip_refs")

    def page(cursor: str | None) -> tuple[list[HipReferenceRecord], str | None, bool]:
        """Fetch a single page of PRs, stopping past the cutoff."""
        data = client.graphql(query, {"owner": owner, "repo": repo, "cursor": cursor})
        nodes, next_cursor, has_next = extract_graphql_cursor_page(data, ["repository", "pullRequests"])

        records: list[HipReferenceRecord] = []
        page_has_older_prs = False
        for node in nodes:
            if node_older_than(node, since):
                page_has_older_prs = True
            records.extend(HipReferenceRecord.from_github_node(node, {"owner": owner, "repo": repo}))

        return records, next_cursor, has_next and not page_has_older_prs

    return paginate_cursor(page)


# Fetch-time floor: pagination never descends past the start of the Hiero
# era. Pre-era PRs are out of scope for HIP analytics, so neither the first
# full fetch nor the deltas pay rate-limit budget (or dataset bytes) for
# them. A pre-era-merged PR can still arrive when something bumps its
# updatedAt — the analysis layer's era filter is the semantic gate.
_HIERO_ERA_START_AT = datetime.fromisoformat(HIERO_ERA_START).replace(tzinfo=UTC)


def fetch_org_pr_hip_refs_graphql(
    client: GitHubClient,
    org: str,
    max_workers: int = GITHUB_MAX_WORKERS,
    *,
    refresh: bool = False,
) -> list[HipReferenceRecord]:
    """Fetch org-wide PR HIP references incrementally, bounded to the Hiero era.

    The "full" fetch is a since-fetch from the era start; deltas fetch from
    the stored watermark (never below the era floor). The fingerprint names
    the bound so the dataset can never be confused with an unbounded sweep.
    """

    def bounded_fetch(since: datetime) -> list[HipReferenceRecord]:
        cutoff = max(since, _HIERO_ERA_START_AT)
        return fetch_org_records_batched(
            client,
            org,
            query_text=load_query("pr_hip_refs"),
            model_class=HipReferenceRecord,
            nodes_path=["pullRequests"],
            stop_node=lambda node: node_older_than(node, cutoff),
            per_repo=lambda repo: fetch_repo_pr_hip_refs_since_graphql(client, repo.owner, repo.name, cutoff),
            task_desc=f"organization {PR_HIP_REFS_RESOURCE.task_desc}",
            max_workers=max_workers,
        )

    return fetch_org_incremental(
        PR_HIP_REFS_RESOURCE,
        org=org,
        full_fetch=lambda: bounded_fetch(_HIERO_ERA_START_AT),
        since_fetch=bounded_fetch,
        fingerprint="hiero-era",
        refresh=refresh,
    )


# --------------------------------------------------------------- HIP inventory

# Frontmatter keys lifted into HipSpecRecord ("type" is renamed: it shadows the
# builtin and "hip_type" reads better in CSVs).
_FRONTMATTER_STR_KEYS = ("title", "status", "category", "created", "updated", "release")


def parse_hip_frontmatter(filename: str, text: str) -> HipSpecRecord | None:
    """Parse one spec file's YAML frontmatter into a :class:`HipSpecRecord`.

    Returns None (logged) for files without a well-formed frontmatter block or
    a numeric ``hip`` field — the proposals repo also holds templates and
    non-spec documents.
    """
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        fields = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        logger.warning("Unparseable frontmatter in %s; skipping", filename)
        return None
    if not isinstance(fields, dict):
        return None
    try:
        number = int(str(fields.get("hip", "")).strip())
    except ValueError:
        logger.debug("No numeric hip number in %s; skipping", filename)
        return None

    def text_of(key: str) -> str:
        value = fields.get(key)
        return str(value).strip() if value is not None else ""

    values = {key: text_of(key) for key in _FRONTMATTER_STR_KEYS}
    updated_at = _parse_frontmatter_date(values["updated"]) or _parse_frontmatter_date(values["created"])
    return HipSpecRecord(number=number, hip_type=text_of("type"), updated_at=updated_at, **values)


def _parse_frontmatter_date(value: str) -> datetime | None:
    """Best-effort UTC datetime from a frontmatter date string.

    Frontmatter dates are bare (``2024-09-19``), so the shared parser's result
    is naive; the dataset store compares watermarks in UTC.
    """
    parsed = parse_github_datetime(value)
    return parsed if parsed is None or parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _fetch_hip_inventory_tree(client: GitHubClient, proposals_repo: str) -> list[HipSpecRecord]:
    """Read every spec file's frontmatter from the proposals repo in one query."""
    owner, _, repo = proposals_repo.partition("/")
    payload = client.graphql(
        load_query("hip_files"),
        {"owner": owner, "repo": repo, "expression": f"HEAD:{HIP_PROPOSALS_DIR}"},
    )
    # client.graphql returns the full response envelope; unwrap "data" like the
    # cursor-pagination helpers do internally.
    repository = (payload.get("data") or {}).get("repository") or {}
    tree = repository.get("object") or {}
    records = []
    for entry in tree.get("entries") or []:
        if not entry.get("name", "").endswith(".md"):
            continue
        text = (entry.get("object") or {}).get("text") or ""
        record = parse_hip_frontmatter(entry["name"], text)
        if record is not None:
            records.append(record)
    logger.info("HIP inventory: %d specs parsed from %s", len(records), proposals_repo)
    return records


def fetch_hip_inventory(
    client: GitHubClient,
    *,
    proposals_repo: str = HIP_PROPOSALS_REPO,
    refresh: bool = False,
) -> list[HipSpecRecord]:
    """The canonical HIP inventory, persisted through the dataset store.

    The fetch is one cheap tree query, so the "delta" is simply a full re-read
    merged by HIP number; persistence buys offline runs and cross-pipeline
    reuse, not bandwidth.
    """
    full_fetch = lambda: _fetch_hip_inventory_tree(client, proposals_repo)  # noqa: E731
    return fetch_incremental(
        path=dataset_path("hip_inventory", proposals_repo),
        model_class=HipSpecRecord,
        key_of=lambda record: record.number,
        updated_at_of=lambda record: record.updated_at,
        full_fetch=full_fetch,
        since_fetch=lambda _since: full_fetch(),
        force_full=refresh,
        full_refresh_after=timedelta(days=30),
    )
