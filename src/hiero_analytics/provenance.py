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
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from hiero_analytics.config.paths import DATASETS_DIR, PROJECT_ROOT

logger = logging.getLogger(__name__)

# How long to let a git subprocess run before giving up. Provenance is a nicety;
# it must never be the reason a multi-hour analytics run stalls.
_GIT_TIMEOUT_SECONDS = 5

# `save_dataset` writes {"version", "fetched_at", "fetched_through", "records"}
# in that order, so both stamps land in the first few dozen bytes. Reading a
# fixed prefix and matching it keeps the per-figure stamp cheap — a full
# `json.load` of every dataset on every chart would dominate the render time.
_WATERMARK_PREFIX_BYTES = 256
_WATERMARK_RE = re.compile(r'"fetched_through"\s*:\s*"([^"]+)"')
# Freshness comes from `fetched_at` (wall clock at write), never from
# `fetched_through` (a *content* watermark). The HIP inventory watermarks itself
# from frontmatter `updated:` dates, so a fortnight with no HIP edits used to
# report the whole dashboard as a fortnight stale.
_FETCHED_AT_RE = re.compile(r'"fetched_at"\s*:\s*"([^"]+)"')
# The key alone, to tell "written before this field existed" from "field is
# there but damaged" — only the first may be skipped.
_FETCHED_AT_KEY_RE = re.compile(r'"fetched_at"\s*:')
# Presence of the schema version marks a file as a `save_dataset` product, which
# is what separates "damaged dataset" from "not a dataset" when no watermark is
# found. Both keys are written before the records, well inside the prefix.
_VERSION_RE = re.compile(r'"version"\s*:')


class _Unknown:
    """Sentinel type: a dataset exists but its watermark cannot be determined."""

    __slots__ = ()

    def __repr__(self) -> str:
        """Name the sentinel in logs and test failures."""
        return "<unknown watermark>"


_UNKNOWN = _Unknown()

# Datasets already reported as predating the ``fetched_at`` stamp. The notice is
# per-file and self-healing, so it is worth saying once a run and never again.
_warned_legacy_datasets: set[str] = set()

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
    run_id: str | None = None

    def footer(self, record_count: int | Mapping[str, int] | None = None) -> str:
        """Render the one-line stamp for a figure footer or dashboard header.

        Unresolvable parts are omitted rather than rendered as "unknown", so a
        local run without git history still gets a useful data stamp.

        ``record_count`` takes a mapping for a figure that plots more than one
        series (``{"GFIs": 120, "contributors": 85}`` → ``n=GFIs 120,
        contributors 85``). A single total would let one series collapse while
        the sum held steady, which is the failure the count exists to catch.

        The run id is included when present because the watermark, revision, and
        count can all repeat across runs whose archived datasets differ — a
        dataset edited in place moves no watermark. The run id resolves the
        figure to exactly one ``dataset-snapshot-<run>-<sha>`` artifact.
        """
        parts: list[str] = []
        if self.data_as_of is not None:
            parts.append(f"data {self.data_as_of.strftime(_STAMP_FORMAT)}")
        if self.git_sha:
            parts.append(f"code {self.git_sha}")
        if self.run_id:
            parts.append(f"run {self.run_id}")
        if isinstance(record_count, Mapping):
            if record_count:
                parts.append("n=" + ", ".join(f"{label} {count:,}" for label, count in record_count.items()))
        elif record_count is not None:
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
    """Oldest ``fetched_at`` across the persisted datasets, or None.

    This is the run's freshness bound — "every dataset was refreshed at least
    this recently" — so it reads the wall-clock write stamp, *not*
    ``fetched_through``. That one is a content watermark: the HIP inventory
    derives it from frontmatter ``updated:`` dates, so using it here reported a
    fortnight-old dashboard whenever the HIP repository sat quiet for a
    fortnight, even though the fetch had just run.

    The *oldest* rather than newest stamp: it is the only figure that holds for
    the dashboard as a whole, since a chart may draw on any dataset.

    Returns None — no claim at all — when a dataset is unreadable. Skipping it
    instead would let the *remaining* datasets set a newer bound, asserting a
    freshness the run cannot support: the corrupt file might hold the oldest
    data of all. Files that were never stamped (the pretty-printed governance
    snapshots that share this directory) are not datasets and are ignored.

    A dataset written before ``fetched_at`` existed contributes its
    ``fetched_through`` content watermark instead: that stamp can only
    *understate* the file's freshness (content precedes the write), so the
    bound stays honest for charts still reading the unstamped file, rather
    than letting the stamped datasets assert a freshness it cannot support.
    The field is additive, so every live dataset acquires ``fetched_at`` on
    the next successful run and the fallback retires itself.
    """
    stamps: list[datetime] = []
    for path in _dataset_files(datasets_dir):
        stamp = _read_stamp(path, _FETCHED_AT_RE)
        if stamp is _UNKNOWN:
            fallback = _read_stamp(path, _WATERMARK_RE) if _predates_fetched_at(path) else None
            if isinstance(fallback, datetime):
                # Once per file per process: provenance resolves per *figure*
                # (deliberately — see the docstring), so warning on every pass
                # buried a real run's log under hundreds of repeats of the same
                # transient, self-healing notice.
                if path.name not in _warned_legacy_datasets:
                    _warned_legacy_datasets.add(path.name)
                    logger.warning(
                        "Dataset %s predates the fetched_at stamp; using its fetched_through "
                        "watermark as a conservative data-as-of bound until the next run stamps it",
                        path.name,
                    )
                stamps.append(fallback)
                continue
            logger.warning(
                "Dataset %s is unreadable; reporting no data-as-of rather than a bound the "
                "remaining datasets cannot support",
                path.name,
            )
            return None
        if stamp is not None:
            stamps.append(stamp)
    return min(stamps) if stamps else None


def _dataset_files(datasets_dir: Path | None = None) -> list[Path]:
    """Persisted dataset files, manifest excluded, in a stable order."""
    directory = datasets_dir if datasets_dir is not None else DATASETS_DIR
    return sorted(path for path in directory.glob("*.json") if path.name != SNAPSHOT_MANIFEST_NAME)


def _read_stamp(path: Path, pattern: re.Pattern[str]) -> datetime | None | _Unknown:
    """Extract a timestamp field from a dataset file's leading bytes.

    Three outcomes, because "no watermark" and "unreadable watermark" must not
    collapse into one answer: a :data:`_UNKNOWN` sentinel when the file looks
    like a persisted dataset but its watermark cannot be read (truncated,
    corrupt, unparseable stamp), None when it is not a watermarked dataset at
    all, and the timestamp otherwise. Only the sentinel invalidates the
    run-level bound.
    """
    try:
        with path.open("r", encoding="utf-8") as handle:
            prefix = handle.read(_WATERMARK_PREFIX_BYTES)
    except OSError:
        # Cannot even read it, so cannot rule out that it is a dataset.
        return _UNKNOWN
    match = pattern.search(prefix)
    if match is None:
        # `save_dataset` writes "version" then both stamps, all well inside the
        # prefix. A "version" with no stamp is therefore a damaged dataset,
        # while neither key means a file this module does not own.
        return _UNKNOWN if _VERSION_RE.search(prefix) else None
    try:
        stamp = datetime.fromisoformat(match.group(1))
    except ValueError:
        return _UNKNOWN
    # Normalize to UTC rather than merely labelling it: `_STAMP_FORMAT` hard-codes
    # "UTC", so an offset-bearing watermark ("...T09:00:00-04:00") would otherwise
    # render as "09:00 UTC" — four hours earlier than the instant it names.
    return stamp.astimezone(UTC) if stamp.tzinfo is not None else stamp.replace(tzinfo=UTC)


def _predates_fetched_at(path: Path) -> bool:
    """True when a readable dataset simply predates the ``fetched_at`` stamp.

    Separates an old-format file — no ``fetched_at`` key, but a content
    watermark that parses — from a damaged one, where the key is present but
    unreadable or the file was truncated mid-write. Only the first is safe to
    skip; a damaged file still withdraws the run-level claim, because it may
    hold the oldest data of all.
    """
    try:
        with path.open("r", encoding="utf-8") as handle:
            prefix = handle.read(_WATERMARK_PREFIX_BYTES)
    except OSError:
        return False
    if _FETCHED_AT_KEY_RE.search(prefix) is not None:
        return False
    return isinstance(_read_stamp(path, _WATERMARK_RE), datetime)


def resolve_provenance(datasets_dir: Path | None = None) -> Provenance:
    """Resolve the current run's provenance.

    Not cached: pipelines fetch and plot interleaved, so a watermark cached at
    the first chart would understate the freshness of every chart after it.
    Reading a 256-byte prefix per dataset is cheap enough to repeat per figure.
    """
    return Provenance(
        data_as_of=dataset_watermark(datasets_dir),
        git_sha=git_sha(),
        run_id=os.getenv("GITHUB_RUN_ID", "").strip() or None,
    )


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
    datasets = [_manifest_entry(dataset) for dataset in _dataset_files(datasets_dir)]
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


def _manifest_entry(dataset: Path) -> dict[str, object]:
    """Describe one dataset for the manifest.

    Both stamps ride along, because they answer different questions when
    tracing a chart back: ``fetched_through`` is how far the *content* was read,
    ``fetched_at`` is when the read happened.

    ``watermark_unreadable`` appears only when the watermark could not be
    determined, so the manifest distinguishes a file that was never watermarked
    (null, unremarkable) from one whose watermark is damaged (the reason the
    run-level ``data_as_of`` is null).
    """
    stamp = _read_stamp(dataset, _WATERMARK_RE)
    fetched_at = _read_stamp(dataset, _FETCHED_AT_RE)
    entry: dict[str, object] = {
        "name": dataset.name,
        "fetched_through": stamp.isoformat() if isinstance(stamp, datetime) else None,
        "fetched_at": fetched_at.isoformat() if isinstance(fetched_at, datetime) else None,
        "bytes": dataset.stat().st_size,
        "sha256": _file_sha256(dataset),
    }
    if stamp is _UNKNOWN:
        entry["watermark_unreadable"] = True
    return entry


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
