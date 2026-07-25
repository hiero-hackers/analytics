"""Tests for run provenance: watermark resolution, revision, and the manifest."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hiero_analytics import provenance
from hiero_analytics.provenance import (
    SNAPSHOT_MANIFEST_NAME,
    Provenance,
    dataset_watermark,
    resolve_provenance,
    write_snapshot_manifest,
)


def _write_dataset(directory: Path, name: str, fetched_through: str | None, records: int = 2) -> Path:
    """Write a dataset file shaped like ``dataset_store.save_dataset`` output."""
    payload: dict[str, object] = {"version": 2}
    if fetched_through is not None:
        payload["fetched_through"] = fetched_through
    payload["records"] = [{"id": index} for index in range(records)]
    path = directory / name
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _clear_git_cache():
    """Isolate each test from the others: ``git_sha`` is cached for the process."""
    provenance.git_sha.cache_clear()
    yield
    provenance.git_sha.cache_clear()


# -------------------------
# Dataset watermark
# -------------------------
def test_watermark_is_the_oldest_across_datasets(tmp_path):
    """The oldest bound is the only one that holds for a dashboard drawing on any dataset."""
    _write_dataset(tmp_path, "issues_org_all.json", "2026-07-20T09:00:00+00:00")
    _write_dataset(tmp_path, "prs_org_all.json", "2026-07-25T09:00:00+00:00")

    assert dataset_watermark(tmp_path) == datetime(2026, 7, 20, 9, 0, tzinfo=UTC)


def test_watermark_is_none_without_datasets(tmp_path):
    """An empty directory yields no stamp rather than a fabricated one."""
    assert dataset_watermark(tmp_path) is None


def test_watermark_skips_files_carrying_none(tmp_path):
    """A dataset with no watermark is skipped, not treated as current."""
    _write_dataset(tmp_path, "governance_config.json", None)
    _write_dataset(tmp_path, "issues_org_all.json", "2026-07-22T09:00:00+00:00")

    assert dataset_watermark(tmp_path) == datetime(2026, 7, 22, 9, 0, tzinfo=UTC)


def test_watermark_skips_corrupt_files_instead_of_raising(tmp_path):
    """A half-written or unparseable dataset must not take down every chart."""
    (tmp_path / "truncated.json").write_text('{"version":2,"fetched_th', encoding="utf-8")
    (tmp_path / "garbage.json").write_text("not json at all", encoding="utf-8")
    _write_dataset(tmp_path, "issues_org_all.json", "2026-07-23T09:00:00+00:00")

    assert dataset_watermark(tmp_path) == datetime(2026, 7, 23, 9, 0, tzinfo=UTC)


def test_watermark_treats_a_naive_timestamp_as_utc(tmp_path):
    """Older datasets stored a naive stamp; it is UTC, matching the fetch layer."""
    _write_dataset(tmp_path, "issues_org_all.json", "2026-07-24T09:00:00")

    assert dataset_watermark(tmp_path) == datetime(2026, 7, 24, 9, 0, tzinfo=UTC)


def test_watermark_rejects_an_unparseable_timestamp(tmp_path):
    """A malformed stamp is no stamp, not a crash."""
    _write_dataset(tmp_path, "issues_org_all.json", "the day before yesterday")

    assert dataset_watermark(tmp_path) is None


def test_watermark_ignores_the_manifest_beside_the_datasets(tmp_path):
    """Counting the manifest's own timestamp would make every run look fresher than its data."""
    _write_dataset(tmp_path, "issues_org_all.json", "2026-07-20T09:00:00+00:00")
    write_snapshot_manifest(tmp_path / SNAPSHOT_MANIFEST_NAME, datasets_dir=tmp_path)

    assert dataset_watermark(tmp_path) == datetime(2026, 7, 20, 9, 0, tzinfo=UTC)


def test_watermark_survives_a_realistically_large_dataset(tmp_path):
    """The prefix read is an optimization; it must still find the stamp before the records."""
    _write_dataset(tmp_path, "issues_org_all.json", "2026-07-21T09:00:00+00:00", records=20_000)

    assert dataset_watermark(tmp_path) == datetime(2026, 7, 21, 9, 0, tzinfo=UTC)


# -------------------------
# Code revision
# -------------------------
def test_git_sha_prefers_the_ci_revision(monkeypatch):
    """In Actions the checked-out revision is authoritative and needs no subprocess."""
    monkeypatch.setenv("GITHUB_SHA", "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678")

    assert provenance.git_sha() == "a1b2c3d"


def test_git_sha_falls_back_to_git_locally(monkeypatch):
    """Outside CI the revision comes from the working tree."""
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    monkeypatch.setattr(provenance, "_run_git", lambda *args: "abc1234" if args[0] == "rev-parse" else "")

    assert provenance.git_sha() == "abc1234"


def test_git_sha_flags_a_dirty_tree(monkeypatch):
    """A chart drawn from uncommitted code is reproducible from no revision — say so."""
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    monkeypatch.setattr(
        provenance,
        "_run_git",
        lambda *args: "abc1234" if args[0] == "rev-parse" else " M src/foo.py",
    )

    assert provenance.git_sha() == "abc1234-dirty"


def test_git_sha_is_none_when_git_is_unavailable(monkeypatch):
    """No git, no claim about the revision."""
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    monkeypatch.setattr(provenance, "_run_git", lambda *_args: None)

    assert provenance.git_sha() is None


def test_run_git_survives_a_missing_binary(monkeypatch):
    """A machine without git still renders charts."""

    def _boom(*_args, **_kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(provenance.subprocess, "run", _boom)

    assert provenance._run_git("rev-parse", "--short", "HEAD") is None


# -------------------------
# Footer rendering
# -------------------------
def test_footer_renders_data_code_and_count():
    """The full stamp is one line, thousands-separated for scanability."""
    stamp = Provenance(data_as_of=datetime(2026, 7, 25, 9, 14, tzinfo=UTC), git_sha="abc1234")

    assert stamp.footer(1284) == "data 2026-07-25 09:14 UTC · code abc1234 · n=1,284"


def test_footer_omits_unresolvable_parts():
    """A local run without datasets still gets a useful revision stamp."""
    stamp = Provenance(data_as_of=None, git_sha="abc1234")

    assert stamp.footer() == "code abc1234"


def test_footer_is_empty_when_nothing_is_known():
    """Nothing to say is better than stamping "unknown" across every chart."""
    assert Provenance(data_as_of=None, git_sha=None).footer() == ""


def test_footer_renders_a_zero_count():
    """An empty chart is when the count matters most, so zero must not be dropped."""
    assert Provenance(data_as_of=None, git_sha=None).footer(0) == "n=0"


# -------------------------
# Resolution
# -------------------------
def test_provenance_is_not_cached_between_charts(tmp_path, monkeypatch):
    """Pipelines fetch and plot interleaved; a cached watermark would stale every later chart."""
    monkeypatch.setenv("GITHUB_SHA", "abc1234def")
    _write_dataset(tmp_path, "issues_org_all.json", "2026-07-20T09:00:00+00:00")
    first = resolve_provenance(tmp_path)

    _write_dataset(tmp_path, "issues_org_all.json", "2026-07-25T09:00:00+00:00")
    second = resolve_provenance(tmp_path)

    assert first.data_as_of < second.data_as_of


# -------------------------
# Snapshot manifest
# -------------------------
def test_manifest_describes_every_dataset(tmp_path, monkeypatch):
    """The archive has to be self-describing: revision, watermarks, and content hashes."""
    monkeypatch.setenv("GITHUB_SHA", "abc1234def")
    _write_dataset(tmp_path, "issues_org_all.json", "2026-07-20T09:00:00+00:00")
    _write_dataset(tmp_path, "prs_org_all.json", "2026-07-25T09:00:00+00:00")

    path = write_snapshot_manifest(tmp_path / SNAPSHOT_MANIFEST_NAME, datasets_dir=tmp_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))

    assert manifest["git_sha"] == "abc1234"
    assert manifest["data_as_of"] == "2026-07-20T09:00:00+00:00"
    assert [dataset["name"] for dataset in manifest["datasets"]] == [
        "issues_org_all.json",
        "prs_org_all.json",
    ]
    assert all(len(dataset["sha256"]) == 64 for dataset in manifest["datasets"])
    assert all(dataset["bytes"] > 0 for dataset in manifest["datasets"])


def test_manifest_records_failed_pipelines(tmp_path):
    """A partial run still archives; the failure list is what marks the snapshot incomplete."""
    _write_dataset(tmp_path, "issues_org_all.json", "2026-07-20T09:00:00+00:00")

    path = write_snapshot_manifest(
        tmp_path / SNAPSHOT_MANIFEST_NAME,
        datasets_dir=tmp_path,
        failures=["scorecard", "difficulty"],
    )

    assert json.loads(path.read_text(encoding="utf-8"))["failed_pipelines"] == ["scorecard", "difficulty"]


def test_manifest_hashes_track_the_data(tmp_path):
    """The SHA-256 is what ties a chart to byte-identical inputs, not a reused filename."""
    _write_dataset(tmp_path, "issues_org_all.json", "2026-07-20T09:00:00+00:00", records=2)
    first = json.loads(write_snapshot_manifest(tmp_path / SNAPSHOT_MANIFEST_NAME, datasets_dir=tmp_path).read_text())

    _write_dataset(tmp_path, "issues_org_all.json", "2026-07-20T09:00:00+00:00", records=3)
    second = json.loads(write_snapshot_manifest(tmp_path / SNAPSHOT_MANIFEST_NAME, datasets_dir=tmp_path).read_text())

    assert first["datasets"][0]["sha256"] != second["datasets"][0]["sha256"]


def test_manifest_is_written_even_with_no_datasets(tmp_path):
    """An empty snapshot is a finding worth recording, not a reason to skip the record."""
    path = write_snapshot_manifest(tmp_path / "nested" / SNAPSHOT_MANIFEST_NAME, datasets_dir=tmp_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))

    assert manifest["datasets"] == []
    assert manifest["data_as_of"] is None
    assert datetime.fromisoformat(manifest["generated_at"]) <= datetime.now(UTC) + timedelta(seconds=1)


def test_manifest_prefers_an_explicit_run_id(tmp_path, monkeypatch):
    """Callers can override the ambient CI run id (tests, backfills, local archives)."""
    monkeypatch.setenv("GITHUB_RUN_ID", "from-env")

    path = write_snapshot_manifest(tmp_path / SNAPSHOT_MANIFEST_NAME, datasets_dir=tmp_path, run_id="explicit")

    assert json.loads(path.read_text(encoding="utf-8"))["run_id"] == "explicit"
