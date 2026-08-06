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


def _write_dataset(
    directory: Path,
    name: str,
    fetched_at: str | None,
    records: int = 2,
    *,
    fetched_through: str | None = "2026-01-01T00:00:00+00:00",
) -> Path:
    """Write a dataset file shaped like ``dataset_store.save_dataset`` output.

    ``fetched_at`` (wall clock at write) is what freshness reads; the content
    watermark defaults to something old and irrelevant precisely so a test that
    cares about freshness fails if the two are ever conflated again.
    """
    payload: dict[str, object] = {"version": 2}
    if fetched_at is not None:
        payload["fetched_at"] = fetched_at
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


def test_watermark_ignores_files_that_are_not_datasets(tmp_path):
    """The governance snapshots share this directory but were never watermarked.

    They carry no schema version, which is what separates them from a dataset
    whose watermark is damaged.
    """
    (tmp_path / "governance_config.json").write_text(
        '{\n  "repositories": [\n    {"name": ".github"}\n  ]\n}', encoding="utf-8"
    )
    _write_dataset(tmp_path, "issues_org_all.json", "2026-07-22T09:00:00+00:00")

    assert dataset_watermark(tmp_path) == datetime(2026, 7, 22, 9, 0, tzinfo=UTC)


def test_a_damaged_dataset_withdraws_the_run_level_claim(tmp_path):
    """One unreadable dataset means no data-as-of at all, not a bound from the rest.

    Skipping the damaged file would let the surviving datasets set a *newer*
    bound — but the unreadable one may hold the oldest data of all, so the
    remaining files cannot support any claim. No stamp beats a false one.
    """
    (tmp_path / "truncated.json").write_text('{"version":2,"fetched_th', encoding="utf-8")
    _write_dataset(tmp_path, "issues_org_all.json", "2026-07-23T09:00:00+00:00")

    assert dataset_watermark(tmp_path) is None


def test_an_unreadable_stamp_withdraws_the_claim_too(tmp_path):
    """A dataset whose timestamp will not parse is damaged, not absent."""
    _write_dataset(tmp_path, "bad.json", "the day before yesterday")
    _write_dataset(tmp_path, "issues_org_all.json", "2026-07-23T09:00:00+00:00")

    assert dataset_watermark(tmp_path) is None


def test_freshness_ignores_the_content_watermark(tmp_path):
    """A stale ``fetched_through`` on a freshly-written dataset must not age the run.

    The regression this pins: the HIP inventory watermarks itself from
    frontmatter ``updated:`` dates, so a fortnight with no HIP edits reported
    the whole dashboard as a fortnight stale even though the fetch had just run.
    """
    _write_dataset(
        tmp_path,
        "hip_inventory_org_all.json",
        "2026-08-06T09:00:00+00:00",  # fetched minutes ago
        fetched_through="2026-07-19T00:00:00+00:00",  # newest HIP edit, weeks old
    )

    assert dataset_watermark(tmp_path) == datetime(2026, 8, 6, 9, 0, tzinfo=UTC)


def test_a_dataset_written_before_fetched_at_bounds_via_its_watermark(tmp_path):
    """An old-format file contributes its content watermark, not nothing.

    Skipping it would let the stamped datasets assert a freshness the run
    cannot support while a chart still reads the unstamped file. The content
    watermark can only understate the file's freshness, so the bound stays
    honest — and the field is additive, so the fallback retires itself on the
    next run that rewrites the file.
    """
    _write_dataset(tmp_path, "legacy_org_all.json", None, fetched_through="2026-01-01T00:00:00+00:00")
    _write_dataset(tmp_path, "issues_org_all.json", "2026-08-06T09:00:00+00:00")

    assert dataset_watermark(tmp_path) == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


def test_a_damaged_fetched_at_still_withdraws_the_claim(tmp_path):
    """Present-but-unparseable is damage, not the old format — no bound at all."""
    _write_dataset(tmp_path, "bad.json", "the day before yesterday")
    _write_dataset(tmp_path, "issues_org_all.json", "2026-08-06T09:00:00+00:00")

    assert dataset_watermark(tmp_path) is None


def test_the_real_writer_produces_a_readable_freshness_stamp(tmp_path):
    """Guard the coupling: provenance parses what ``save_dataset`` actually writes.

    Every other test here hand-builds the payload, so a change to the writer's
    field set or key order would otherwise leave them all green while the real
    stamp went unreadable.
    """
    from hiero_analytics.data_sources.dataset_store import save_dataset
    from hiero_analytics.data_sources.models import ScorecardRecord

    before = datetime.now(UTC)
    save_dataset(
        tmp_path / "written_org_all.json",
        [ScorecardRecord(repo="r", score=8.0, checks={}, date=datetime(2026, 7, 19, tzinfo=UTC))],
        fetched_through=datetime(2026, 7, 19, tzinfo=UTC),
    )

    stamp = dataset_watermark(tmp_path)
    assert stamp is not None
    assert before <= stamp <= datetime.now(UTC)


def test_watermark_treats_a_naive_timestamp_as_utc(tmp_path):
    """Older datasets stored a naive stamp; it is UTC, matching the fetch layer."""
    _write_dataset(tmp_path, "issues_org_all.json", "2026-07-24T09:00:00")

    assert dataset_watermark(tmp_path) == datetime(2026, 7, 24, 9, 0, tzinfo=UTC)


def test_watermark_converts_an_offset_to_the_utc_instant(tmp_path):
    """An offset stamp must be converted, not relabelled.

    The footer format hard-codes "UTC", so leaving 09:00-04:00 as-is would print
    "09:00 UTC" — four hours earlier than the instant it names.
    """
    _write_dataset(tmp_path, "issues_org_all.json", "2026-07-20T09:00:00-04:00")

    assert dataset_watermark(tmp_path) == datetime(2026, 7, 20, 13, 0, tzinfo=UTC)


def test_oldest_is_chosen_on_true_instants_not_wall_clock(tmp_path):
    """Comparing un-normalized stamps would pick the wrong dataset as oldest."""
    _write_dataset(tmp_path, "a.json", "2026-07-20T09:00:00-04:00")  # 13:00 UTC
    _write_dataset(tmp_path, "b.json", "2026-07-20T11:00:00+00:00")  # 11:00 UTC

    assert dataset_watermark(tmp_path) == datetime(2026, 7, 20, 11, 0, tzinfo=UTC)


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


def test_footer_reports_each_series_separately():
    """A single total would hide one series collapsing while the sum held steady."""
    stamp = Provenance(data_as_of=None, git_sha=None)

    assert stamp.footer({"GFIs": 120, "contributors": 85}) == "n=GFIs 120, contributors 85"


def test_footer_omits_an_empty_series_mapping():
    """No series is not the same as a series of zero; say nothing."""
    assert Provenance(data_as_of=None, git_sha=None).footer({}) == ""


def test_footer_carries_the_run_id():
    """Watermark, revision, and count can repeat across runs whose archives differ.

    A dataset edited in place moves no watermark, so the run id is what resolves a
    standalone PNG to exactly one dataset-snapshot artifact.
    """
    stamp = Provenance(data_as_of=None, git_sha="abc1234", run_id="17654321")

    assert stamp.footer(5) == "code abc1234 · run 17654321 · n=5"


def test_run_id_comes_from_the_ci_environment(tmp_path, monkeypatch):
    """Locally there is no run id, and the footer simply omits it."""
    monkeypatch.setenv("GITHUB_RUN_ID", "17654321")
    assert resolve_provenance(tmp_path).run_id == "17654321"

    monkeypatch.delenv("GITHUB_RUN_ID")
    assert resolve_provenance(tmp_path).run_id is None


def test_manifest_flags_a_damaged_dataset(tmp_path):
    """The manifest must distinguish "never watermarked" from "watermark broken".

    The second is the reason the run-level data_as_of is null, so a reader of the
    archive needs to see which file caused it.
    """
    _write_dataset(tmp_path, "good.json", "2026-07-25T09:00:00+00:00")
    (tmp_path / "trunc.json").write_text('{"version":2,"fetched_th', encoding="utf-8")

    path = write_snapshot_manifest(tmp_path / SNAPSHOT_MANIFEST_NAME, datasets_dir=tmp_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    entries = {entry["name"]: entry for entry in manifest["datasets"]}

    assert entries["trunc.json"]["watermark_unreadable"] is True
    assert entries["trunc.json"]["fetched_through"] is None
    assert "watermark_unreadable" not in entries["good.json"]
    # Every file is still hashed — a damaged dataset is exactly what you want to
    # identify byte-for-byte later.
    assert all(len(entry["sha256"]) == 64 for entry in manifest["datasets"])
    assert manifest["data_as_of"] is None


def test_the_legacy_dataset_notice_is_logged_once_per_run(tmp_path, caplog):
    """Provenance resolves per figure, so a per-pass warning floods the log."""
    provenance._warned_legacy_datasets.clear()
    _write_dataset(tmp_path, "legacy_org_all.json", None, fetched_through="2026-01-01T00:00:00+00:00")
    _write_dataset(tmp_path, "issues_org_all.json", "2026-08-06T09:00:00+00:00")

    with caplog.at_level("WARNING"):
        for _ in range(5):  # five charts in one run
            dataset_watermark(tmp_path)

    assert sum("predates the fetched_at stamp" in record.message for record in caplog.records) == 1
