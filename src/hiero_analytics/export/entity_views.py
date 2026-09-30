"""The repository and contributor detail documents of the data API.

Built from the ``entity_activity`` pipeline's tables
(:mod:`hiero_analytics.dashboard_spec.entities` names them) plus, for a
repository, the optional per-repository tables other pipelines write. Nothing is
re-aggregated here: every count was computed from the underlying events by the
pipeline, per window. This module only selects each entity's rows, completes
periods with no activity as zeros, and shapes the documents:

- two **indexes** per org, listing every repository and contributor with a detail
  document, so the dashboard knows which names to link, and
- one **detail document** per repository and per contributor, fetched only when a
  reader opens it.

Documents carry ``schema_version: 1``. Like the rest of v1 they only ever gain
fields; a breaking change moves to a new API version.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from hiero_analytics.analysis.entity_activity import FAMILY_FIELDS
from hiero_analytics.dashboard_spec import entities as spec
from hiero_analytics.domain.periods import ACTIVITY_PERIODS
from hiero_analytics.domain.repos import bare_repo
from hiero_analytics.export.chart_data import chart_document

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
ALL_TIME = "all"
COUNT_FIELDS = tuple(spec.COUNT_LABELS)

# Ids become file names and URL values: lower-case GitHub login / repository
# characters only, never a path separator. A leading dot (``.github``) becomes
# an underscore so no document is a hidden file; the dashboard finds ids through
# the index, so they need not be derivable from the name.
_ID = re.compile(r"^[a-z0-9_][a-z0-9._-]*$")

Freshness = Callable[[Path], dict]
# A published table's file name -> the dashboard sections it feeds ({macro, id, title}).
SourceSections = dict[str, list[dict]]


@dataclass
class EntityDocuments:
    """The org's entity documents keyed by API-relative path, and its manifest entry."""

    manifest_entry: dict
    documents: dict[str, dict] = field(default_factory=dict)


def entity_id(name: str) -> str | None:
    """The id a repository (bare or ``owner/repo``) or login is published under, or None."""
    candidate = bare_repo(str(name)).strip().lower()
    if candidate.startswith("."):
        candidate = f"_{candidate.lstrip('.')}"
    return candidate if _ID.match(candidate) and candidate != "_" else None


def _read(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path, dtype={"repo": str, "contributor": str, "period": str, "month": str})


def _grouped(frame: pd.DataFrame | None, key: str) -> dict[str, pd.DataFrame]:
    """A table's rows split by ``key`` once, rather than filtered per entity."""
    return {} if frame is None or frame.empty else {str(name): rows for name, rows in frame.groupby(key)}


def _json_rows(frame: pd.DataFrame) -> list[dict]:
    """JSON-safe records: NaN -> null, numpy scalars -> Python."""
    return json.loads(frame.to_json(orient="records", date_format="iso") or "[]")


def _windows(window_end: str | None, data_through: str | None = None) -> dict:
    """The dates each published window covers; ``end`` is when the analysis ran.

    ``data_through`` is the latest tracked event in the organisation: a reader can
    tell a quiet week from activity datasets that had not been refreshed.
    """
    end = datetime.fromisoformat(window_end) if window_end else None
    periods = [
        {
            "key": period.key,
            "label": period.label,
            "days": period.days,
            "start": (end - timedelta(days=period.days)).isoformat() if end and period.days else None,
        }
        for period in ACTIVITY_PERIODS
    ]
    return {
        "end": window_end,
        "data_through": data_through,
        "periods": [*periods, {"key": ALL_TIME, "label": "All time", "days": None}],
    }


def _summary(rows: pd.DataFrame, extra: tuple[str, ...]) -> dict:
    """Counts per window, zero-filled for windows with no tracked activity."""
    fields = (*COUNT_FIELDS, "total_actions", *extra)
    by_period = rows.set_index("period")
    summary = {}
    for key in (ALL_TIME, *(period.key for period in ACTIVITY_PERIODS)):
        row = by_period.loc[key] if key in by_period.index else None
        summary[key] = {name: int(row[name]) if row is not None else 0 for name in fields}
    return summary


def _mix(summary: dict) -> dict:
    """The work mix per window: each family's actions and integer share of all actions."""
    mix = {}
    for key, counts in summary.items():
        total = counts["total_actions"]
        mix[key] = {}
        for family, fields in FAMILY_FIELDS.items():
            count = sum(counts[name] for name in fields)
            mix[key][family] = {"count": count, "share": round(count / total * 100) if total else 0}
    return mix


def _trend(rows: pd.DataFrame | None, key: str, source: Path, org: str, freshness: dict) -> dict | None:
    """One entity's monthly activity (its rows of a monthly table) as a stacked timeseries chart."""
    if rows is None or rows.empty:
        return None
    rows = rows.drop(columns=key)
    document = chart_document(
        {
            "kind": "timeseries",
            "category": "month",
            "frequency": "month",
            "category_label": "Month (UTC)",
            "series": [{"key": field_name, "label": label} for field_name, label in spec.COUNT_LABELS.items()],
            "metric": "tracked_actions",
            "unit": "Tracked actions",
            "population": spec.REPOSITORY_POPULATION if key == "repo" else spec.CONTRIBUTOR_POPULATION,
            "mark": "bar",
            "stacked": True,
        },
        source,
        org,
        freshness.get("generated_at"),
        table=rows.reset_index(drop=True),
    )
    # One id for every entity's trend: a reader's chart settings (style, span,
    # hidden series) carry from one detail view to the next.
    document["id"] = f"{'repository' if key == 'repo' else 'contributor'}-trend"
    return {**document, **freshness}


def _activity_table(
    pairs: pd.DataFrame,
    *,
    table_id: str,
    title: str,
    description: str,
    first: tuple[str, str],
    columns: list[tuple],
    source: str,
    freshness: dict,
) -> dict:
    """A section-shaped table (all-time rows plus period variants) the dashboard's table renders."""
    keys = [first[0], *(column[0] for column in columns)]

    def rows(period: str) -> list[dict]:
        scoped = pairs[pairs["period"] == period].sort_values("last_active", ascending=False)
        return _json_rows(scoped[keys])

    document = {
        "id": table_id,
        "title": title,
        "description": description,
        "source": source,
        "columns": [
            {"key": first[0], "label": first[1]},
            *({"key": key, "label": label, **({"format": fmt[0]} if fmt else {})} for key, label, *fmt in columns),
        ],
        "rows": rows(ALL_TIME),
        "periods": {period.key: rows(period.key) for period in ACTIVITY_PERIODS},
        **freshness,
    }
    document["row_count"] = len(document["rows"])
    return document


_COUNT_COLUMNS = [(name, label, "number") for name, label in spec.COUNT_LABELS.items()]
_TOTAL_COLUMN = ("total_actions", "All tracked actions", "number")
_LAST_ACTIVE_COLUMN = ("last_active", "Last active (UTC)", "date")


def _related_row(frame: pd.DataFrame, repo_id: str) -> pd.DataFrame:
    """The rows of a per-repository table for one repository (bare or owner/repo names)."""
    if "repo" not in frame.columns:
        return frame.iloc[0:0]
    ids = frame["repo"].astype(str).map(entity_id)
    return frame[ids == repo_id]


class _Tables:
    """Each optional table read once per emit (None when it was not produced)."""

    def __init__(self, org_data_dir: Path, freshness: Freshness) -> None:
        self._dir, self._freshness, self._frames, self._fresh = org_data_dir, freshness, {}, {}

    def frame(self, name: str) -> pd.DataFrame | None:
        if name not in self._frames:
            self._frames[name] = _read(self._dir / name)
        return self._frames[name]

    def freshness(self, name: str) -> dict:
        if name not in self._fresh:
            self._fresh[name] = self._freshness(self._dir / name)
        return self._fresh[name]


def _links(files: list[str], sources: SourceSections) -> list[dict]:
    """The published dashboard sections these tables feed, each once, in file order."""
    links: list[dict] = []
    for name in files:
        for section in sources.get(name, []):
            if all(link["id"] != section["id"] for link in links):
                links.append(section)
    return links


def _related(repo_id: str, tables: _Tables, sources: SourceSections) -> tuple[list[dict], list[str]]:
    """The optional release, governance, onboarding and security sections for one repository.

    Returns ``(sections, unavailable)``: a section whose table was not produced by
    this run is named in ``unavailable`` instead; one produced without a row for
    this repository is published with no fields, which the view states.
    """
    sections, unavailable = [], []
    for section_id, declared in spec.REPO_RELATED.items():
        frame = tables.frame(declared["file"])
        if frame is None:
            unavailable.append(declared["title"])
            continue
        files = [declared["file"]]
        fields = []
        for part in [{"file": declared["file"], "columns": declared["columns"]}, *declared.get("extra", [])]:
            part_frame = tables.frame(part["file"])
            if part_frame is None:
                continue
            if part["file"] not in files:
                files.append(part["file"])
            match = _related_row(part_frame, repo_id)
            if match.empty:
                continue
            row = _json_rows(match.head(1))[0]
            for key, label, *fmt in part["columns"]:
                if key in row and row[key] is not None:
                    fields.append(
                        {"key": key, "label": label, "value": row[key], **({"format": fmt[0]} if fmt else {})}
                    )
        section = {
            "id": section_id,
            "title": declared["title"],
            "source": files,
            "fields": fields,
            **tables.freshness(declared["file"]),
        }
        if listing := declared.get("list"):
            list_frame = tables.frame(listing["file"])
            if list_frame is not None:
                matches = _related_row(list_frame, repo_id)
                keys = [column[0] for column in listing["columns"] if column[0] in matches.columns]
                if not matches.empty and keys:
                    ascending = listing["sort"] != "published_at"
                    matches = matches.sort_values(listing["sort"], ascending=ascending)
                    if limit := listing.get("limit"):
                        matches = matches.head(limit)
                    section["list"] = {
                        "title": listing["title"],
                        "source": listing["file"],
                        "columns": [
                            {"key": key, "label": label, **({"format": fmt[0]} if fmt else {})}
                            for key, label, *fmt in listing["columns"]
                            if key in keys
                        ],
                        "rows": _json_rows(matches[keys]),
                        **tables.freshness(listing["file"]),
                    }
                if listing["file"] not in files:
                    files.append(listing["file"])
        # Every figure leads back to the dashboard section it came from.
        section["links"] = _links(files, sources)
        sections.append(section)
    return sections, unavailable


def _head(kind: str, org: str, entity: str, freshness: dict, window: dict) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "org": org,
        "id": entity,
        **freshness,
        "scope": spec.SCOPE,
        "methodology": spec.METHODOLOGY,
        "limits": spec.LIMITS,
        "window": window,
    }


def build_entity_documents(
    org: str,
    org_data_dir: Path,
    freshness: Freshness,
    sources: SourceSections | None = None,
) -> EntityDocuments | None:
    """Every entity document for ``org``, or None when the entity tables were not produced.

    ``sources`` maps each table the org published to the dashboard sections it
    feeds, so a repository's joined figures can link back to their evidence.
    """
    repos = _read(org_data_dir / spec.REPO_ACTIVITY_FILE)
    contributors = _read(org_data_dir / spec.CONTRIBUTOR_ACTIVITY_FILE)
    pairs = _read(org_data_dir / spec.PAIR_ACTIVITY_FILE)
    if repos is None or contributors is None or pairs is None:
        return None
    tables = _Tables(org_data_dir, freshness)
    repo_monthly = _grouped(tables.frame(spec.REPO_MONTHLY_FILE), "repo")
    contributor_monthly = _grouped(tables.frame(spec.CONTRIBUTOR_MONTHLY_FILE), "contributor")
    pairs_by_repo = _grouped(pairs, "repo")
    pairs_by_contributor = _grouped(pairs, "contributor")
    repo_freshness = freshness(org_data_dir / spec.REPO_ACTIVITY_FILE)
    contributor_freshness = freshness(org_data_dir / spec.CONTRIBUTOR_ACTIVITY_FILE)
    pair_freshness = freshness(org_data_dir / spec.PAIR_ACTIVITY_FILE)

    def stamp(column: str) -> str | None:
        return next(iter(repos[column].dropna()), None) if column in repos else None

    window = _windows(stamp("window_end"), stamp("data_through"))
    base = f"{org}/entities"
    out = EntityDocuments(manifest_entry={})

    repo_index, seen = [], set()
    for repo_key, rows in repos.groupby("repo"):
        full_name = str(repo_key)
        repo_id = entity_id(full_name)
        if repo_id is None or repo_id in seen:
            logger.warning("Skipping repository %r: no unique, safe id", full_name)
            continue
        seen.add(repo_id)
        name = bare_repo(full_name)
        summary = _summary(rows, ("active_contributors",))
        all_time = rows[rows["period"] == ALL_TIME].iloc[0]
        repo_pairs = pairs_by_repo.get(full_name, pairs.iloc[0:0])
        related, unavailable = _related(repo_id, tables, sources or {})
        document = {
            **_head("repository", org, repo_id, repo_freshness, window),
            "name": name,
            "full_name": full_name,
            "github_url": f"https://github.com/{full_name}",
            "population": spec.REPOSITORY_POPULATION,
            "source": [spec.REPO_ACTIVITY_FILE, spec.PAIR_ACTIVITY_FILE, spec.REPO_MONTHLY_FILE],
            "first_active": all_time["first_active"],
            "last_active": all_time["last_active"],
            "summary": summary,
            "mix": _mix(summary),
            "trend": _trend(
                repo_monthly.get(full_name),
                "repo",
                org_data_dir / spec.REPO_MONTHLY_FILE,
                org,
                tables.freshness(spec.REPO_MONTHLY_FILE),
            ),
            "contributors": _activity_table(
                repo_pairs,
                table_id="repository-contributors",
                title="Active contributors",
                description="Everyone with a tracked action in this repository in the window, most recently active first.",
                first=("contributor", "Contributor"),
                columns=[
                    *_COUNT_COLUMNS,
                    _TOTAL_COLUMN,
                    ("building_share", "Building & fixing", "percent"),
                    ("reviewing_share", "Reviewing & guiding", "percent"),
                    ("organizing_share", "Organizing & answering", "percent"),
                    _LAST_ACTIVE_COLUMN,
                ],
                source=spec.PAIR_ACTIVITY_FILE,
                freshness=pair_freshness,
            ),
            "related": related,
            "unavailable": unavailable,
        }
        out.documents[f"{base}/repositories/{repo_id}.json"] = document
        repo_index.append(
            {
                "id": repo_id,
                "name": name,
                "full_name": full_name,
                "total_actions": summary[ALL_TIME]["total_actions"],
                "active_contributors": summary[ALL_TIME]["active_contributors"],
                "last_active": all_time["last_active"],
            }
        )

    contributor_index, seen = [], set()
    for login_key, rows in contributors.groupby("contributor"):
        login = str(login_key)
        contributor_id = entity_id(login)
        if contributor_id is None or contributor_id in seen:
            logger.warning("Skipping contributor %r: no unique, safe id", login)
            continue
        seen.add(contributor_id)
        summary = _summary(rows, ("repos_touched",))
        all_time = rows[rows["period"] == ALL_TIME].iloc[0]
        document = {
            **_head("contributor", org, contributor_id, contributor_freshness, window),
            "login": login,
            "github_url": f"https://github.com/{login}",
            "population": spec.CONTRIBUTOR_POPULATION,
            "source": [spec.CONTRIBUTOR_ACTIVITY_FILE, spec.PAIR_ACTIVITY_FILE, spec.CONTRIBUTOR_MONTHLY_FILE],
            "first_active": all_time["first_active"],
            "last_active": all_time["last_active"],
            "summary": summary,
            "mix": _mix(summary),
            "trend": _trend(
                contributor_monthly.get(login),
                "contributor",
                org_data_dir / spec.CONTRIBUTOR_MONTHLY_FILE,
                org,
                tables.freshness(spec.CONTRIBUTOR_MONTHLY_FILE),
            ),
            "repositories": _activity_table(
                pairs_by_contributor.get(login, pairs.iloc[0:0]),
                table_id="contributor-repositories",
                title="Repositories",
                description="Each repository with a tracked action by this person in the window, most recent first.",
                first=("repo", "Repository"),
                columns=[
                    *_COUNT_COLUMNS,
                    _TOTAL_COLUMN,
                    ("first_active", "First active (UTC)", "date"),
                    _LAST_ACTIVE_COLUMN,
                ],
                source=spec.PAIR_ACTIVITY_FILE,
                freshness=pair_freshness,
            ),
        }
        out.documents[f"{base}/contributors/{contributor_id}.json"] = document
        contributor_index.append(
            {
                "id": contributor_id,
                "login": login,
                "total_actions": summary[ALL_TIME]["total_actions"],
                "repos_touched": summary[ALL_TIME]["repos_touched"],
                "last_active": all_time["last_active"],
            }
        )

    for kind, rows, freshness_of, population in (
        ("repositories", repo_index, repo_freshness, spec.REPOSITORY_POPULATION),
        ("contributors", contributor_index, contributor_freshness, spec.CONTRIBUTOR_POPULATION),
    ):
        path = f"{base}/{kind}.json"
        out.documents[path] = {
            "schema_version": SCHEMA_VERSION,
            "kind": f"{kind}-index",
            "org": org,
            **freshness_of,
            "source": spec.REPO_ACTIVITY_FILE if kind == "repositories" else spec.CONTRIBUTOR_ACTIVITY_FILE,
            "scope": spec.SCOPE,
            "population": population,
            "window": window,
            # Where each row's detail document lives: substitute its id.
            "detail_path": f"{base}/{kind}/{{id}}.json",
            "rows": sorted(rows, key=lambda entry: entry["id"]),
        }
        out.manifest_entry[kind] = {"path": path, "count": len(rows)}
    return out
