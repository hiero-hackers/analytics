"""What each dataset refresh did, and whether the result is plausible.

The dataset store fails safe on purpose: a repository that cannot be fetched
holds its watermark instead of failing the run, so the night's progress is
saved and the next run resumes. The cost is that a problem can persist without
anyone noticing, and a mistake in this layer shifts the published numbers
without an error. Each incremental fetch therefore records a
:class:`DatasetRefresh` here. ``run_all`` writes them to ``SNAPSHOT.json``
(``dataset_refresh``) and the job summary, and :func:`problems` decides the
health check, which the workflow runs as its own job *after* the datasets are
saved (see ``.github/workflows/update-analytics.yml``).

What fails the check:

- a repository whose watermark has been held for ``HOLD_FAIL_AFTER`` runs in a row;
- rows lost by a repository that was neither fully refreshed nor retired. A
  delta merge can only add or update rows, so a loss outside a full refresh is
  a bug, not news;
- a repository whose last full refresh is older than its refresh window plus
  ``OVERDUE_GRACE``: the self-heal is not keeping up.

What only warns: a hold that has not yet reached the threshold, refreshes
deferred by the nightly budget, and a dataset that has not shrunk for
``MONOTONIC_WARN_AFTER`` runs. The last is the self-heal's symptom in #623,
but on its own it is not a failure: event datasets are append-only, and an
issues dataset grows on net through any night with more new issues than
deletions.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Any

# Consecutive runs a repository's watermark may be held before the health check fails.
HOLD_FAIL_AFTER = 3
# How far past its refresh window a repository's last full refresh may lag (a
# missed night or two, a deferral) before the health check fails.
OVERDUE_GRACE = timedelta(days=7)
# Runs without the row count ever going down before a dataset is called out.
MONOTONIC_WARN_AFTER = 30

# The key a single-file dataset (no per-repository state) reports its figures under.
WHOLE_DATASET = "(whole dataset)"


@dataclass
class DatasetRefresh:
    """One dataset's refresh in this run.

    ``held`` maps each repository whose fetch failed to the number of
    consecutive runs it has now been held. ``unexplained_loss`` maps a
    repository to the rows it lost although it was neither fully refreshed nor
    retired. ``overdue`` maps a repository to its ``last_full_at`` when that is
    older than the refresh window plus ``OVERDUE_GRACE``.
    """

    dataset: str
    rows_before: int
    rows_after: int
    full_refreshed: list[str] = field(default_factory=list)
    backfilled: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    held: dict[str, int] = field(default_factory=dict)
    retired: list[str] = field(default_factory=list)
    unexplained_loss: dict[str, int] = field(default_factory=dict)
    overdue: dict[str, str] = field(default_factory=dict)
    runs_without_shrink: int = 0

    def to_json(self) -> dict[str, Any]:
        """The JSON form recorded in ``SNAPSHOT.json``."""
        return asdict(self)


_lock = threading.Lock()
_refreshes: dict[str, DatasetRefresh] = {}


def record(refresh: DatasetRefresh) -> None:
    """Note what a dataset's refresh did. A dataset refreshed twice in one run keeps its latest."""
    with _lock:
        _refreshes[refresh.dataset] = refresh


def recorded() -> list[DatasetRefresh]:
    """Every refresh recorded in this process, by dataset name."""
    with _lock:
        return [_refreshes[name] for name in sorted(_refreshes)]


def forget() -> None:
    """Start a fresh record: at the start of each run, and between tests."""
    with _lock:
        _refreshes.clear()


def problems(refreshes: Iterable[DatasetRefresh]) -> list[str]:
    """What fails the health check, one line each."""
    found: list[str] = []
    for refresh in refreshes:
        for repo, holds in sorted(refresh.held.items()):
            if holds >= HOLD_FAIL_AFTER:
                found.append(f"{refresh.dataset}: {repo} has been held for {holds} runs in a row")
        for repo, lost in sorted(refresh.unexplained_loss.items()):
            found.append(f"{refresh.dataset}: {repo} lost {lost} rows without a full refresh or retirement")
        for repo, last_full_at in sorted(refresh.overdue.items()):
            found.append(f"{refresh.dataset}: {repo} has not been fully refreshed since {last_full_at}")
    return found


def warnings(refreshes: Iterable[DatasetRefresh]) -> list[str]:
    """What the summary calls out without failing the check, one line each."""
    found: list[str] = []
    for refresh in refreshes:
        for repo, holds in sorted(refresh.held.items()):
            if holds < HOLD_FAIL_AFTER:
                found.append(f"{refresh.dataset}: {repo} held this run ({holds} in a row)")
        if refresh.deferred:
            found.append(
                f"{refresh.dataset}: {len(refresh.deferred)} due full refreshes deferred by the nightly budget"
            )
        if refresh.runs_without_shrink >= MONOTONIC_WARN_AFTER:
            found.append(f"{refresh.dataset}: has not shrunk in {refresh.runs_without_shrink} runs")
    return found


def summary(refreshes: Iterable[DatasetRefresh]) -> dict[str, Any]:
    """The ``dataset_refresh`` block of ``SNAPSHOT.json``."""
    refreshes = list(refreshes)
    return {
        "healthy": not problems(refreshes),
        "problems": problems(refreshes),
        "warnings": warnings(refreshes),
        "datasets": {refresh.dataset: refresh.to_json() for refresh in refreshes},
    }


def render_markdown(block: dict[str, Any]) -> str:
    """The ``dataset_refresh`` block as a job-summary section."""
    datasets = block.get("datasets") or {}
    if not datasets:
        return ""
    verdict = "healthy" if block.get("healthy") else "**unhealthy: the dataset health check fails this run**"
    lines = ["## Dataset refresh", "", f"Datasets are {verdict}.", ""]
    for heading, items in (("Problems", block.get("problems")), ("Warnings", block.get("warnings"))):
        if items:
            lines += [f"### {heading}", "", *(f"- {item}" for item in items), ""]
    lines += [
        "| Dataset | Rows before | Rows after | Full refreshes | of which backfills | Deferred | Held | Retired |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, entry in datasets.items():
        lines.append(
            f"| {name} | {entry['rows_before']} | {entry['rows_after']} | {len(entry['full_refreshed'])} "
            f"| {len(entry['backfilled'])} | {len(entry['deferred'])} | {len(entry['held'])} "
            f"| {len(entry['retired'])} |"
        )
    return "\n".join(lines) + "\n\n"
