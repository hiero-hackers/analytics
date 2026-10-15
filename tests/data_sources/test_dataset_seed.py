"""Tests for seeding the local dataset cache from the nightly CI snapshot artifact."""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from hiero_analytics.data_sources import dataset_seed
from hiero_analytics.data_sources.dataset_seed import SeedError, seed_datasets

REPO = "some-owner/some-repo"
RUN_URL = f"https://github.com/{REPO}/actions/runs/222"
ARTIFACT_URL = f"https://api.github.com/repos/{REPO}/actions/artifacts/9/zip"

DATASET = {"version": 2, "fetched_at": "2026-10-15T01:00:00+00:00", "fetched_through": "2026-10-15T00:59:00+00:00"}
MANIFEST = {"git_sha": "abc1234", "data_as_of": "2026-10-15T01:00:00+00:00", "run_id": "222", "datasets": []}


def make_zip(entries: dict[str, object]) -> bytes:
    """Build an in-memory zip; dict values are JSON-encoded, bytes are stored as is."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content if isinstance(content, bytes) else json.dumps(content))
    return buffer.getvalue()


def good_zip() -> bytes:
    """A snapshot like the nightly one: two datasets, a governance config and the manifest."""
    return make_zip(
        {
            "issues_org_OPEN.json": {**DATASET, "records": []},
            "merged_pr_difficulty_org_all.json": {**DATASET, "records": [{"a": 1}]},
            "governance_config_org_all.json": {"repositories": [], "teams": []},
            "SNAPSHOT.json": MANIFEST,
        }
    )


class FakeClient:
    """Stands in for GitHubClient: canned JSON by URL, canned zip bytes, and a call log."""

    def __init__(self, *, runs=None, artifacts=None, archive=None):
        """Configure responses; ``runs`` is a list of answers to the runs listing, consumed in order."""
        default_run = {"id": 222, "html_url": RUN_URL, "created_at": "2026-10-15"}
        default_artifact = {"name": "dataset-snapshot-222-abc", "archive_download_url": ARTIFACT_URL}
        self.runs = list(runs if runs is not None else [[default_run]])
        self.artifacts = artifacts if artifacts is not None else [default_artifact]
        self.archive = archive if archive is not None else good_zip()
        self.get_calls: list[tuple[str, dict]] = []
        self.bytes_calls: list[str] = []

    def get(self, url, **kwargs):
        """Answer the runs listing and the artifacts listing."""
        self.get_calls.append((url, kwargs))
        if url.endswith("/runs"):
            return {"workflow_runs": self.runs.pop(0) if self.runs else []}
        return {"artifacts": self.artifacts}

    def get_bytes(self, url):
        """Return the canned archive."""
        self.bytes_calls.append(url)
        return self.archive


class PerRunClient(FakeClient):
    """A fake whose artifact listing depends on the run id in the URL."""

    def __init__(self, runs, listings):
        """Serve ``runs`` as the runs listing and ``listings[run_id]`` as that run's artifacts."""
        super().__init__(runs=[runs])
        self.listings = listings

    def get(self, url, **kwargs):
        """Route artifact listings by run id."""
        if url.endswith("/runs"):
            return super().get(url, **kwargs)
        self.get_calls.append((url, kwargs))
        return {"artifacts": self.listings[int(url.split("/")[-2])]}


@pytest.fixture(autouse=True)
def token(monkeypatch):
    """Give every test a token unless it removes it."""
    monkeypatch.setattr(dataset_seed, "GITHUB_TOKEN", "test-token")


def test_seed_writes_files_and_reports_provenance(tmp_path):
    """The happy path writes every archive file and reports run, revision and data-as-of."""
    client = FakeClient()
    destination = tmp_path / "seeded"

    result = seed_datasets(client, REPO, datasets_dir=destination)

    assert sorted(path.name for path in destination.iterdir()) == [
        "SNAPSHOT.json",
        "governance_config_org_all.json",
        "issues_org_OPEN.json",
        "merged_pr_difficulty_org_all.json",
    ]
    assert json.loads((destination / "issues_org_OPEN.json").read_text())["version"] == 2
    assert result.run_id == 222
    assert result.run_url == RUN_URL
    assert result.git_sha == "abc1234"
    assert result.data_as_of == "2026-10-15T01:00:00+00:00"
    assert result.dataset_count == 3
    assert client.bytes_calls == [ARTIFACT_URL]

    summary = dataset_seed.format_summary(result)
    assert "222" in summary
    assert RUN_URL in summary
    assert "abc1234" in summary
    assert "2026-10-15T01:00:00+00:00" in summary
    assert "3 dataset file(s)" in summary


def test_seed_queries_only_successful_scheduled_runs_first(tmp_path):
    """Failed runs are skipped by construction: the query asks for status=success and schedule events."""
    client = FakeClient()

    seed_datasets(client, REPO, datasets_dir=tmp_path / "d")

    url, kwargs = client.get_calls[0]
    assert url == f"https://api.github.com/repos/{REPO}/actions/workflows/update-analytics.yml/runs"
    assert kwargs["params"]["status"] == "success"
    assert kwargs["params"]["event"] == "schedule"
    assert kwargs["params"]["per_page"] == 5


def test_seed_falls_back_to_any_successful_event(tmp_path):
    """With no successful scheduled run, the same query without the event filter is tried."""
    client = FakeClient(runs=[[], [{"id": 222, "html_url": RUN_URL, "created_at": "x"}]])

    result = seed_datasets(client, REPO, datasets_dir=tmp_path / "d")

    run_queries = [kwargs["params"] for url, kwargs in client.get_calls if url.endswith("/runs")]
    assert "event" in run_queries[0]
    assert "event" not in run_queries[1]
    assert run_queries[1]["status"] == "success"
    assert result.run_id == 222


def test_seed_picks_newest_run_and_skips_runs_without_a_snapshot(tmp_path):
    """The newest run wins first; runs whose artifact expired or is missing are passed over."""
    runs = [
        {"id": 1, "html_url": "u1", "created_at": "2026-10-01"},
        {"id": 3, "html_url": "u3", "created_at": "2026-10-03"},
        {"id": 2, "html_url": "u2", "created_at": "2026-10-02"},
    ]
    client = PerRunClient(
        runs,
        {
            3: [{"name": "dataset-snapshot-3-x", "archive_download_url": "z3", "expired": True}],
            2: [{"name": "other-artifact", "archive_download_url": "zo"}],
            1: [{"name": "dataset-snapshot-1-x", "archive_download_url": "z1"}],
        },
    )

    result = seed_datasets(client, REPO, datasets_dir=tmp_path / "d")

    assert result.run_id == 1
    assert client.bytes_calls == ["z1"]


def test_seed_with_run_id_skips_the_runs_listing(tmp_path):
    """An explicit --run-id goes straight to that run's artifacts."""
    client = FakeClient()

    result = seed_datasets(client, REPO, run_id=777, datasets_dir=tmp_path / "d")

    assert [url for url, _ in client.get_calls] == [f"https://api.github.com/repos/{REPO}/actions/runs/777/artifacts"]
    assert result.run_id == 777
    assert result.run_url == f"https://github.com/{REPO}/actions/runs/777"


def test_seed_without_a_successful_run_fails(tmp_path):
    """No successful run at all is an error that says what to try."""
    client = FakeClient(runs=[[], []])

    with pytest.raises(SeedError, match="No successful run"):
        seed_datasets(client, REPO, datasets_dir=tmp_path / "d")


def test_seed_without_a_snapshot_artifact_fails(tmp_path):
    """A run with no dataset-snapshot artifact is an error, and nothing is downloaded."""
    client = FakeClient(artifacts=[{"name": "site", "archive_download_url": "z"}])

    with pytest.raises(SeedError, match=r"dataset-snapshot-\*"):
        seed_datasets(client, REPO, datasets_dir=tmp_path / "d")
    assert client.bytes_calls == []


def test_seed_without_a_token_fails_before_any_request(monkeypatch, tmp_path):
    """No GITHUB_TOKEN is refused up front, explaining that artifact downloads need one."""
    monkeypatch.setattr(dataset_seed, "GITHUB_TOKEN", None)
    client = FakeClient()

    with pytest.raises(SeedError, match="GITHUB_TOKEN"):
        seed_datasets(client, REPO, datasets_dir=tmp_path / "d")
    assert client.get_calls == []


@pytest.mark.parametrize("bad_repo", ["no-slash", "a/b/c", "owner/na me", "../x/y", ""])
def test_seed_rejects_a_malformed_repo(bad_repo, tmp_path):
    """--repo must be OWNER/NAME, so it cannot smuggle path segments into API URLs."""
    with pytest.raises(SeedError, match="OWNER/NAME"):
        seed_datasets(FakeClient(), bad_repo, datasets_dir=tmp_path / "d")


@pytest.mark.parametrize("name", ["sub/issues.json", "..\\issues.json", "../issues.json", "a..b.json", "/abs.json"])
def test_seed_rejects_entries_that_are_not_flat_basenames(name, tmp_path):
    """A path separator or '..' in an entry name rejects the whole archive before anything is written."""
    archive = make_zip({"SNAPSHOT.json": MANIFEST, name: {**DATASET, "records": []}})
    destination = tmp_path / "seeded"

    with pytest.raises(SeedError, match="flat file name"):
        seed_datasets(FakeClient(archive=archive), REPO, datasets_dir=destination)
    assert not destination.exists()


def test_seed_rejects_non_json_entries(tmp_path):
    """An entry that does not end in .json is refused."""
    archive = make_zip({"SNAPSHOT.json": MANIFEST, "run.sh": b"echo hi"})

    with pytest.raises(SeedError, match=r"not a \.json file"):
        seed_datasets(FakeClient(archive=archive), REPO, datasets_dir=tmp_path / "d")


def test_seed_rejects_unparseable_json(tmp_path):
    """A .json entry that does not parse is refused and nothing is written."""
    archive = make_zip({"SNAPSHOT.json": MANIFEST, "issues_org_OPEN.json": b"{not json"})
    destination = tmp_path / "seeded"

    with pytest.raises(SeedError, match="not valid JSON"):
        seed_datasets(FakeClient(archive=archive), REPO, datasets_dir=destination)
    assert not destination.exists()


def test_seed_rejects_a_dataset_without_a_version_key(tmp_path):
    """A JSON file that is not a save_dataset product (no 'version') is refused."""
    archive = make_zip({"SNAPSHOT.json": MANIFEST, "issues_org_OPEN.json": {"records": []}})

    with pytest.raises(SeedError, match="no 'version' key"):
        seed_datasets(FakeClient(archive=archive), REPO, datasets_dir=tmp_path / "d")


def test_seed_rejects_a_manifest_without_datasets(tmp_path):
    """SNAPSHOT.json is validated by its 'datasets' key."""
    archive = make_zip({"SNAPSHOT.json": {"git_sha": "x"}})

    with pytest.raises(SeedError, match="'datasets'"):
        seed_datasets(FakeClient(archive=archive), REPO, datasets_dir=tmp_path / "d")


def test_seed_requires_the_manifest(tmp_path):
    """An archive without SNAPSHOT.json is not a snapshot."""
    archive = make_zip({"issues_org_OPEN.json": {**DATASET, "records": []}})

    with pytest.raises(SeedError, match=r"SNAPSHOT\.json"):
        seed_datasets(FakeClient(archive=archive), REPO, datasets_dir=tmp_path / "d")


def test_seed_rejects_an_archive_over_the_size_cap(tmp_path, monkeypatch):
    """The uncompressed size cap is enforced on the bytes actually read."""
    monkeypatch.setattr(dataset_seed, "MAX_UNCOMPRESSED_BYTES", 100)
    archive = make_zip({"SNAPSHOT.json": {**MANIFEST, "pad": "x" * 500}})

    with pytest.raises(SeedError, match="unpacks to more than"):
        seed_datasets(FakeClient(archive=archive), REPO, datasets_dir=tmp_path / "d")


def test_seed_rejects_an_archive_over_the_entry_cap(tmp_path, monkeypatch):
    """Too many entries is refused."""
    monkeypatch.setattr(dataset_seed, "MAX_ENTRIES", 2)

    with pytest.raises(SeedError, match="entries"):
        seed_datasets(FakeClient(), REPO, datasets_dir=tmp_path / "d")


def test_seed_rejects_something_that_is_not_a_zip(tmp_path):
    """A non-zip download is reported as such."""
    with pytest.raises(SeedError, match="not a valid zip"):
        seed_datasets(FakeClient(archive=b"<html>"), REPO, datasets_dir=tmp_path / "d")


def test_seed_refuses_a_non_empty_directory_without_force(tmp_path):
    """Existing files are listed and left alone unless --force is given."""
    destination = tmp_path / "seeded"
    destination.mkdir()
    (destination / "mine.json").write_text("keep me")
    client = FakeClient()

    with pytest.raises(SeedError, match=r"mine\.json"):
        seed_datasets(client, REPO, datasets_dir=destination)

    assert (destination / "mine.json").read_text() == "keep me"
    assert client.get_calls == []


def test_seed_with_force_overwrites_a_non_empty_directory(tmp_path):
    """--force writes over same-named files and leaves other files in place."""
    destination = tmp_path / "seeded"
    destination.mkdir()
    (destination / "issues_org_OPEN.json").write_text("stale")
    (destination / "other.json").write_text("other")

    seed_datasets(FakeClient(), REPO, force=True, datasets_dir=destination)

    assert json.loads((destination / "issues_org_OPEN.json").read_text())["version"] == 2
    assert (destination / "other.json").read_text() == "other"


def test_seed_allows_an_existing_empty_directory(tmp_path):
    """An empty datasets directory counts as empty."""
    destination = tmp_path / "seeded"
    destination.mkdir()

    result = seed_datasets(FakeClient(), REPO, datasets_dir=destination)

    assert result.dataset_count == 3
