"""Run provenance: which data, which code, and how many rows drew an artifact.

Charts are rebuilt from scratch on every refresh and published straight to
GitHub Pages, overwriting the previous deploy. Nothing is committed, so a figure
on its own carries no trace of the dataset watermark or the code revision behind
it — two dashboards that look different give you no way to tell whether the data
moved, the code moved, or both.

This module resolves that provenance from two sources that already exist:

* **Data** — every persisted dataset stores the ``fetched_through`` watermark it
  was fetched to (see :mod:`hiero_analytics.data_sources.dataset_store`). The
  run-level "data as of" is the *oldest* watermark across those datasets: the
  conservative bound, since every source is current at least through that point.
* **Code** — ``GITHUB_SHA`` in CI, otherwise ``git rev-parse``. A dirty working
  tree is flagged, because a chart drawn from uncommitted code is not
  reproducible from any revision.

Record counts are deliberately *not* resolved here. Counting rows in a dataset
means parsing the whole JSON file (they run to tens of MB), whereas the figure
being stamped already holds the frame it plotted — so the count is passed in by
the caller, and :func:`write_snapshot_manifest` records each dataset's SHA-256
instead, which is both cheaper and a stronger identity than a row count.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from hiero_analytics.config.paths import DATASETS_DIR, PROJECT_ROOT

logger = logging.getLogger(__name__)

# How long to let a git subprocess run before giving up. Provenance is a nicety;
# it must never be the reason a multi-hour analytics run stalls.
_GIT_TIMEOUT_SECONDS = 5

# `save_dataset` writes {"version", "fetched_through", "records"} in that order,
# so the watermark always lands in the first few dozen bytes. Reading a fixed
# prefix and matching it keeps the per-figure stamp cheap — a full `json.load`
# of every dataset on every chart would dominate the render time.
_WATERMARK_PREFIX_BYTES = 256
_WATERMARK_RE = re.compile(r'"fetched_through"\s*:\s*"([^"]+)"')

_STAMP_FORMAT = "%Y-%m-%d %H:%M UTC"

# The manifest lives beside the datasets it describes, so that archiving the
# directory archives its own description. It is excluded from every dataset scan
# below — it is not a dataset, and hashing it into itself is meaningless.
SNAPSHOT_MANIFEST_NAME = "SNAPSHOT.json"

# Read the archive in chunks rather than whole: dataset files are tens of MB and
# the manifest hashes all of them in sequence.
_HASH_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class Provenance:
    """The data and code identity of a single analytics run."""

    data_as_of: datetime | None
    git_sha: str | None

    def footer(self, record_count: int | None = None) -> str:
        """Render the one-line stamp for a figure footer or dashboard header.

        Unresolvable parts are omitted rather than rendered as "unknown", so a
        local run without git history still gets a useful data stamp.
        """
        parts: list[str] = []
        if self.data_as_of is not None:
            parts.append(f"data {self.data_as_of.strftime(_STAMP_FORMAT)}")
        if self.git_sha:
            parts.append(f"code {self.git_sha}")
        if record_count is not None:
            parts.append(f"n={record_count:,}")
        return " · ".join(parts)


@lru_cache(maxsize=1)
def git_sha() -> str | None:
    """Return the short revision that is drawing these charts, or None.

    Prefers ``GITHUB_SHA`` so a CI run stamps the exact revision Actions checked
    out. Locally, falls back to ``git rev-parse`` and appends ``-dirty`` when the
    tree has uncommitted changes — a chart stamped ``-dirty`` cannot be
    reproduced from any revision, which is precisely what the reader needs to
    know. Cached: the revision cannot change mid-run.
    """
    if ci_sha := os.getenv("GITHUB_SHA", "").strip():
        return ci_sha[:7]

    head = _run_git("rev-parse", "--short", "HEAD")
    if head is None:
        return None
    # An empty --porcelain output means clean; a failed call means unknown, and
    # we would rather omit the suffix than assert cleanliness we did not verify.
    status = _run_git("status", "--porcelain")
    return f"{head}-dirty" if status else head


def _run_git(*args: str) -> str | None:
    """Run a read-only git command in the project root, or None if it fails.

    Every failure mode is the same non-answer: git missing, not a repository,
    a shallow checkout, or a hung index lock.
    """
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", *args],  # noqa: S607 - resolved from PATH by design
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        logger.debug("git %s unavailable; provenance will omit the revision", " ".join(args))
        return None
    if result.returncode != 0:
        logger.debug("git %s failed: %s", " ".join(args), result.stderr.strip())
        return None
    return result.stdout.strip()


def dataset_watermark(datasets_dir: Path | None = None) -> datetime | None:
    """Oldest ``fetched_through`` across the persisted datasets, or None if absent.

    The *oldest* rather than newest watermark: it is the only figure that holds
    for the dashboard as a whole, since a chart may draw on any dataset. A file
    whose watermark cannot be read is skipped rather than treated as current —
    silently reporting a fresher time than the data supports is the one failure
    mode worth avoiding here.
    """
    stamps = [ts for path in _dataset_files(datasets_dir) if (ts := _read_watermark(path)) is not None]
    return min(stamps) if stamps else None


def _dataset_files(datasets_dir: Path | None = None) -> list[Path]:
    """Persisted dataset files, manifest excluded, in a stable order."""
    directory = datasets_dir if datasets_dir is not None else DATASETS_DIR
    return sorted(path for path in directory.glob("*.json") if path.name != SNAPSHOT_MANIFEST_NAME)


def _read_watermark(path: Path) -> datetime | None:
    """Extract ``fetched_through`` from a dataset file's leading bytes."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            prefix = handle.read(_WATERMARK_PREFIX_BYTES)
    except OSError:
        return None
    match = _WATERMARK_RE.search(prefix)
    if match is None:
        return None
    try:
        stamp = datetime.fromisoformat(match.group(1))
    except ValueError:
        return None
    return stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=UTC)


def resolve_provenance(datasets_dir: Path | None = None) -> Provenance:
    """Resolve the current run's provenance.

    Not cached: pipelines fetch and plot interleaved, so a watermark cached at
    the first chart would understate the freshness of every chart after it.
    Reading a 256-byte prefix per dataset is cheap enough to repeat per figure.
    """
    return Provenance(data_as_of=dataset_watermark(datasets_dir), git_sha=git_sha())


def write_snapshot_manifest(
    path: Path,
    *,
    datasets_dir: Path | None = None,
    failures: list[str] | None = None,
    run_id: str | None = None,
) -> Path:
    """Write the run manifest that makes an archived dataset snapshot self-describing.

    The archive is only useful if you can tell, later, what it is: which
    revision fetched it, how current each dataset was, and which pipelines
    failed during the run that produced it (a partial run still archives, and
    the reader needs to know the snapshot is partial). Each dataset is recorded
    by SHA-256, so a chart can be tied to byte-identical inputs rather than to a
    filename that gets overwritten every five days.
    """
    provenance = resolve_provenance(datasets_dir)
    datasets = [
        {
            "name": dataset.name,
            "fetched_through": stamp.isoformat() if (stamp := _read_watermark(dataset)) else None,
            "bytes": dataset.stat().st_size,
            "sha256": _file_sha256(dataset),
        }
        for dataset in _dataset_files(datasets_dir)
    ]
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "git_sha": provenance.git_sha,
        "data_as_of": provenance.data_as_of.isoformat() if provenance.data_as_of else None,
        "run_id": run_id or os.getenv("GITHUB_RUN_ID") or None,
        "failed_pipelines": failures or [],
        "datasets": datasets,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    logger.info("Wrote snapshot manifest %s (%d dataset(s))", path, len(datasets))
    return path


def _file_sha256(path: Path) -> str | None:
    """Streaming SHA-256 of ``path``, or None if it cannot be read."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(_HASH_CHUNK_BYTES):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()
