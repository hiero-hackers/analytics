"""Seed the local dataset cache from the nightly CI snapshot.

A fresh clone's first run cold-fetches every dataset, which takes the better part
of half an hour and fails whenever GitHub is flaky. The scheduled "Refresh
Analytics Data" workflow already archives the whole ``outputs/data/datasets/``
directory as an Actions artifact every night (``dataset-snapshot-<run>-<sha>``),
so this module downloads the latest *successful* run's artifact and unpacks it
there, after which the first local run is an incremental one.

Trust boundary: the archive is only ever fetched from the configured
repository's own Actions artifacts, through the shared :class:`GitHubClient`
(so headers, authentication and rate-limit handling are shared). The archive is
treated as untrusted input anyway: every entry is validated before anything is
written, so a bad archive leaves the datasets directory untouched.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import requests

from hiero_analytics.config import paths
from hiero_analytics.config.github import BASE_URL, GITHUB_TOKEN
from hiero_analytics.provenance import SNAPSHOT_MANIFEST_NAME

from .github_client import GitHubClient

logger = logging.getLogger(__name__)

# The repository whose Actions artifacts are downloaded; forks pass ``--repo``.
DEFAULT_SEED_REPO = "hiero-hackers/analytics"

# The workflow that produces the snapshot artifact, and the artifact's name prefix.
WORKFLOW_FILE = "update-analytics.yml"
ARTIFACT_PREFIX = "dataset-snapshot-"

# How many recent successful runs to look through for one whose artifact is
# still available (artifacts expire after the retention period).
RUNS_TO_CONSIDER = 5

# Sanity caps on what an archive may unpack to. The real snapshot is about ten
# files and tens of MB; these exist to stop a malformed or hostile archive.
MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
MAX_ENTRIES = 2000

# Governance configs share the datasets directory but are pretty-printed
# configuration, not ``save_dataset`` products, so they carry no ``version``.
_GOVERNANCE_CONFIG_PREFIX = "governance_config_"

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class SeedError(Exception):
    """A seeding step failed; the message is meant to be shown to the user as is."""


@dataclass(frozen=True)
class SeedResult:
    """What was written, and which run it came from."""

    run_id: int
    run_url: str
    git_sha: str | None
    data_as_of: str | None
    dataset_count: int
    total_bytes: int
    datasets_dir: Path


def seed_datasets(
    client: GitHubClient,
    repo: str = DEFAULT_SEED_REPO,
    *,
    run_id: int | None = None,
    force: bool = False,
    datasets_dir: Path | None = None,
) -> SeedResult:
    """Download the latest successful snapshot artifact and unpack it into the datasets directory.

    Args:
        client: The GitHub client (the process-wide shared one in the CLI).
        repo: ``OWNER/NAME`` of the repository whose Actions artifacts to use.
        run_id: Use this workflow run instead of the latest successful one. Also
            the only way to take a failed run's partial snapshot.
        force: Write into a datasets directory that already has files in it,
            overwriting files of the same name.
        datasets_dir: Destination; defaults to ``outputs/data/datasets``.

    Returns:
        A :class:`SeedResult` describing what was written.

    Raises:
        SeedError: On every failure mode, with a message saying what to do about it.
    """
    destination = datasets_dir if datasets_dir is not None else paths.DATASETS_DIR

    if not _REPO_RE.match(repo):
        raise SeedError(f"--repo must look like OWNER/NAME, got {repo!r}")
    if not GITHUB_TOKEN:
        raise SeedError(
            "GITHUB_TOKEN is not set. GitHub only serves Actions artifact downloads to authenticated "
            "requests, even on public repositories. Put GITHUB_TOKEN=<token> in .env (see the README) and retry."
        )
    existing = sorted(path.name for path in destination.iterdir()) if destination.is_dir() else []
    if existing and not force:
        raise SeedError(
            f"{destination} already holds {len(existing)} file(s): {_preview(existing)}. "
            "Refusing to overwrite them; pass --force to write the snapshot over them."
        )

    try:
        archive, resolved_run_id, run_url = _download_snapshot(client, repo, run_id)
    except requests.RequestException as exc:
        raise SeedError(f"GitHub request failed while fetching the snapshot from {repo}: {exc}") from exc

    files = validate_archive(archive)
    _write_files(destination, files)

    manifest = json.loads(files[SNAPSHOT_MANIFEST_NAME])
    return SeedResult(
        run_id=resolved_run_id,
        run_url=run_url,
        git_sha=manifest.get("git_sha"),
        data_as_of=manifest.get("data_as_of"),
        dataset_count=len(files) - 1,  # the manifest is not a dataset
        total_bytes=sum(len(content) for content in files.values()),
        datasets_dir=destination,
    )


def format_summary(result: SeedResult) -> str:
    """Render the one-screen summary printed after a successful seed."""
    return "\n".join(
        [
            f"Seeded {result.dataset_count} dataset file(s), {_format_size(result.total_bytes)}, "
            f"into {result.datasets_dir}",
            f"  run:        {result.run_id} ({result.run_url})",
            f"  code:       {result.git_sha or 'unknown'}",
            f"  data as of: {result.data_as_of or 'unknown'}",
        ]
    )


# --------------------------------------------------------
# DOWNLOAD
# --------------------------------------------------------


def _download_snapshot(client: GitHubClient, repo: str, run_id: int | None) -> tuple[bytes, int, str]:
    """Find the run and artifact, download the archive, and return ``(zip bytes, run id, run URL)``."""
    runs = [_explicit_run(repo, run_id)] if run_id is not None else _successful_runs(client, repo)

    for run in runs:
        artifact = _snapshot_artifact(client, repo, run["id"])
        if artifact is None:
            logger.warning("Run %s has no unexpired %s* artifact; trying an older run", run["id"], ARTIFACT_PREFIX)
            continue
        logger.info("Downloading %s (%s bytes)", artifact["name"], artifact.get("size_in_bytes", "unknown"))
        return client.get_bytes(artifact["archive_download_url"]), run["id"], run["html_url"]

    if run_id is not None:
        raise SeedError(f"Run {run_id} of {repo} has no unexpired {ARTIFACT_PREFIX}* artifact.")
    raise SeedError(
        f"None of the last {RUNS_TO_CONSIDER} successful runs of {WORKFLOW_FILE} in {repo} has an unexpired "
        f"{ARTIFACT_PREFIX}* artifact (they are kept for a limited time). "
        "Pass --run-id to name a run, or run the pipeline to fetch from scratch."
    )


def _explicit_run(repo: str, run_id: int) -> dict[str, Any]:
    """Describe a run the user named, without spending an API call to look it up."""
    return {"id": run_id, "html_url": f"https://github.com/{repo}/actions/runs/{run_id}"}


def _successful_runs(client: GitHubClient, repo: str) -> list[dict[str, Any]]:
    """Recent successful runs of the refresh workflow, newest first.

    ``status=success`` is what excludes failed runs: the workflow archives its
    datasets ``if: always()``, so a failed run has a partial snapshot that must
    not be mistaken for the latest good one. Scheduled runs are preferred (they
    are the unattended, full refresh); a manual dispatch is the fallback.
    """
    url = f"{BASE_URL}/repos/{repo}/actions/workflows/{WORKFLOW_FILE}/runs"
    base_params: dict[str, Any] = {"status": "success", "per_page": RUNS_TO_CONSIDER}
    for params in ({**base_params, "event": "schedule"}, base_params):
        payload = client.get(url, params=params)
        runs = payload.get("workflow_runs", []) if isinstance(payload, dict) else []
        if runs:
            return sorted(runs, key=lambda run: run.get("created_at", ""), reverse=True)
    raise SeedError(
        f"No successful run of {WORKFLOW_FILE} found in {repo}. "
        "If this is a fork, check that its Actions are enabled and have run, or pass --repo/--run-id."
    )


def _snapshot_artifact(client: GitHubClient, repo: str, run_id: int) -> dict[str, Any] | None:
    """The newest unexpired snapshot artifact of a run, or None."""
    payload = client.get(f"{BASE_URL}/repos/{repo}/actions/runs/{run_id}/artifacts")
    artifacts = payload.get("artifacts", []) if isinstance(payload, dict) else []
    candidates = [
        artifact
        for artifact in artifacts
        if str(artifact.get("name", "")).startswith(ARTIFACT_PREFIX)
        and not artifact.get("expired")
        and artifact.get("archive_download_url")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda artifact: artifact.get("created_at", ""))


# --------------------------------------------------------
# VALIDATION
# --------------------------------------------------------


def validate_archive(archive: bytes) -> dict[str, bytes]:
    """Check a snapshot archive in memory and return its files by name.

    Nothing touches the disk until every check has passed. Entries must be flat
    ``*.json`` basenames (no directories, separators or ``..``), the archive must
    stay under the entry and uncompressed-size caps, every file must parse as a
    JSON object, dataset files must carry the ``version`` key ``save_dataset``
    writes, and ``SNAPSHOT.json`` must be present with its ``datasets`` list.

    Raises:
        SeedError: On the first problem found.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(archive))
    except zipfile.BadZipFile as exc:
        raise SeedError(f"The downloaded artifact is not a valid zip archive: {exc}") from exc

    with zf:
        infos = zf.infolist()
        if not infos:
            raise SeedError("The snapshot artifact is empty.")
        if len(infos) > MAX_ENTRIES:
            raise SeedError(f"The snapshot artifact has {len(infos)} entries, over the limit of {MAX_ENTRIES}.")

        files: dict[str, bytes] = {}
        remaining = MAX_UNCOMPRESSED_BYTES
        for info in infos:
            name = info.filename
            _check_entry_name(name)
            if name in files:
                raise SeedError(f"Snapshot artifact lists {name!r} more than once.")
            # Read at most one byte past the budget: the declared size in the
            # header is attacker-controlled, so the bound is enforced on the bytes.
            with zf.open(info) as handle:
                content = handle.read(remaining + 1)
            if len(content) > remaining:
                raise SeedError(
                    f"Snapshot artifact unpacks to more than {MAX_UNCOMPRESSED_BYTES // (1024 * 1024)} MB; refusing."
                )
            remaining -= len(content)
            _check_content(name, content)
            files[name] = content

    if SNAPSHOT_MANIFEST_NAME not in files:
        raise SeedError(f"Snapshot artifact has no {SNAPSHOT_MANIFEST_NAME}; it is not a dataset snapshot.")
    return files


def _check_entry_name(name: str) -> None:
    """Reject anything but a flat ``*.json`` basename."""
    if not name or "/" in name or "\\" in name or ".." in name or "\x00" in name:
        raise SeedError(f"Snapshot artifact entry {name!r} is not a flat file name; refusing to unpack it.")
    if not name.endswith(".json"):
        raise SeedError(f"Snapshot artifact entry {name!r} is not a .json file; refusing to unpack it.")


def _check_content(name: str, content: bytes) -> None:
    """Require valid JSON of the shape the dataset store (or the manifest) writes."""
    try:
        document = json.loads(content)
    except (UnicodeDecodeError, ValueError) as exc:
        raise SeedError(f"Snapshot artifact entry {name!r} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise SeedError(f"Snapshot artifact entry {name!r} is not a JSON object.")

    if name == SNAPSHOT_MANIFEST_NAME:
        if "datasets" not in document:
            raise SeedError(f"{SNAPSHOT_MANIFEST_NAME} in the artifact has no 'datasets' key.")
    elif not name.startswith(_GOVERNANCE_CONFIG_PREFIX) and "version" not in document:
        raise SeedError(f"Snapshot artifact entry {name!r} has no 'version' key, so it is not a dataset file.")


# --------------------------------------------------------
# WRITE
# --------------------------------------------------------


def _write_files(destination: Path, files: dict[str, bytes]) -> None:
    """Write each file via a temp file and rename, so a crash never leaves a half-written dataset."""
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        target = destination / name
        with NamedTemporaryFile("wb", dir=destination, delete=False) as tmp:
            tmp.write(content)
        os.replace(tmp.name, target)


def _preview(names: list[str], limit: int = 5) -> str:
    """A short list of file names for an error message."""
    shown = ", ".join(names[:limit])
    return shown if len(names) <= limit else f"{shown}, ... and {len(names) - limit} more"


def _format_size(size: int) -> str:
    """Human-readable size in MB."""
    return f"{size / (1024 * 1024):.1f} MB"
