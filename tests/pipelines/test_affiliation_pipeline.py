"""Integration tests for the affiliation pipeline orchestration (``main``)."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import matplotlib
import pytest

matplotlib.use("Agg")

import hiero_analytics.pipelines.affiliation as runner
from hiero_analytics.data_sources.models import ContributorActivityRecord

TEST_ORG = "test-org"

# Test data factories


def _test_activity(
    repo: str,
    actor: str,
    activity_type: str = "authored_pull_request",
    days_ago: int = 5,
    number: int = 1,
) -> ContributorActivityRecord:
    """Create a synthetic contributor activity record ``days_ago`` days in the past."""
    return ContributorActivityRecord(
        repo=repo,
        activity_type=activity_type,
        actor=actor,
        occurred_at=datetime.now(UTC) - timedelta(days=days_ago),
        target_type="pull_request",
        target_number=number,
    )


# Fixtures


@pytest.fixture
def governance_config() -> dict:
    """Minimal governance config with maintainer seats on two repos."""
    return {
        "teams": [
            {"name": "sdk-python-maintainers", "maintainers": ["alice"], "members": ["bob"]},
            {"name": "sdk-java-maintainers", "maintainers": ["carol"], "members": ["dave"]},
        ],
        "repositories": [
            {"name": "sdk-python", "teams": {"sdk-python-maintainers": "maintain"}},
            {"name": "sdk-java", "teams": {"sdk-java-maintainers": "maintain"}},
        ],
    }


@pytest.fixture
def affiliations() -> dict[str, str]:
    """Curated login -> organisation map (dave deliberately left unknown)."""
    return {
        "alice": "Acme Corp",
        "bob": "Acme Corp",
        "carol": "Independent",
    }


@pytest.fixture
def synthetic_activity() -> list[ContributorActivityRecord]:
    """Recent activity so the active-maintainer views have a non-empty population."""
    return [
        _test_activity(f"{TEST_ORG}/sdk-python", "alice", "authored_pull_request", days_ago=3, number=1),
        _test_activity(f"{TEST_ORG}/sdk-python", "bob", "reviewed_pull_request", days_ago=10, number=1),
        _test_activity(f"{TEST_ORG}/sdk-java", "carol", "merged_pull_request", days_ago=7, number=2),
        _test_activity(f"{TEST_ORG}/sdk-java", "dave", "authored_issue", days_ago=400, number=3),
    ]


def _patch_pipeline(monkeypatch, tmp_path, config, affiliations, manual_logins, activity):
    """Redirect every external call ``main()`` makes to synthetic in-memory data."""

    def _fake_org_dirs(_org: str) -> tuple[Path, Path]:
        org_data_dir = tmp_path / "data"
        org_charts_dir = tmp_path / "charts"
        org_data_dir.mkdir(parents=True, exist_ok=True)
        org_charts_dir.mkdir(parents=True, exist_ok=True)
        return org_data_dir, org_charts_dir

    monkeypatch.setattr("hiero_analytics.pipelines.affiliation.ensure_org_dirs", _fake_org_dirs)
    monkeypatch.setattr("hiero_analytics.pipelines.affiliation.fetch_governance_config", lambda *_a, **_k: config)
    monkeypatch.setattr("hiero_analytics.pipelines.affiliation.load_affiliations", lambda: affiliations)
    monkeypatch.setattr("hiero_analytics.pipelines.affiliation.load_manual_logins", lambda: manual_logins)
    monkeypatch.setattr("hiero_analytics.pipelines.affiliation.shared_client", MagicMock)
    monkeypatch.setattr(
        "hiero_analytics.pipelines.affiliation.load_contributor_activity",
        lambda _client, _org: activity,
    )


# Tests


def test_main_creates_output_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    governance_config,
    affiliations,
    synthetic_activity,
):
    """Running main() should create the affiliation tables and distribution outputs."""
    _patch_pipeline(
        monkeypatch,
        tmp_path,
        governance_config,
        affiliations,
        {"alice"},
        synthetic_activity,
    )

    runner.main(TEST_ORG)

    data_dir = tmp_path / "data"
    expected_csvs = [
        "maintainer_affiliations.csv",
        "affiliation_distribution.csv",
        "repo_affiliation_diversity.csv",
        "team_affiliation_diversity.csv",
    ]
    for csv_file in expected_csvs:
        csv_path = data_dir / csv_file
        assert csv_path.exists(), f"CSV {csv_file} not created"
        assert os.path.getsize(csv_path) > 0, f"CSV {csv_file} is empty"

    classified = (data_dir / "maintainer_affiliations.csv").read_text(encoding="utf-8")
    assert "alice" in classified
    assert "Acme Corp" in classified
    # alice is hand-corrected in the YAML, the others come from the resolver.
    assert "manual" in classified
    assert "automated" in classified

    distribution = (data_dir / "affiliation_distribution.csv").read_text(encoding="utf-8")
    assert "Acme Corp" in distribution
    assert "Independent" in distribution


def test_main_handles_empty_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Running main() with an empty config, affiliation map, and activity should not crash."""
    _patch_pipeline(monkeypatch, tmp_path, {}, {}, set(), [])

    runner.main(TEST_ORG)

    data_dir = tmp_path / "data"
    # The roster cross-reference is still written (header-only) for an empty org.
    assert (data_dir / "maintainer_affiliations.csv").exists()
    assert (data_dir / "repo_affiliation_diversity.csv").exists()


@pytest.fixture
def committer_governance_config() -> dict:
    """Governance config where frank and grace hold write access and nothing higher."""
    return {
        "teams": [
            {"name": "sdk-python-maintainers", "maintainers": ["alice"], "members": ["bob"]},
            {"name": "sdk-devs", "maintainers": [], "members": ["bob", "frank", "grace"]},
        ],
        "repositories": [
            {"name": "sdk-python", "teams": {"sdk-python-maintainers": "maintain", "sdk-devs": "write"}},
        ],
    }


def test_role_variants_drive_the_outputs_so_a_new_tab_is_one_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Adding a role to ROLE_VARIANTS is all a new tab needs — nothing is hard-coded per role."""
    config = {
        "teams": [
            {"name": "maintainers", "maintainers": ["alice"], "members": []},
            {"name": "triagers", "maintainers": [], "members": ["frank", "grace"]},
        ],
        "repositories": [{"name": "sdk-python", "teams": {"maintainers": "maintain", "triagers": "triage"}}],
    }
    affiliations = {"alice": "Acme Corp", "frank": "Beta LLC", "grace": "Beta LLC"}
    _patch_pipeline(monkeypatch, tmp_path, config, affiliations, set(), [])
    monkeypatch.setattr(runner, "ROLE_VARIANTS", [("maintainer", ""), ("triage", "_triage")])

    runner.main(TEST_ORG)

    data_dir = tmp_path / "data"
    assert (data_dir / "triage_affiliations.csv").exists()
    assert (tmp_path / "charts" / "affiliation_donut_triage.png").exists()
    assert "frank" in (data_dir / "triage_affiliations.csv").read_text(encoding="utf-8")


def test_main_writes_the_committer_variant_alongside_the_maintainer_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    committer_governance_config,
):
    """The committer tab gets its own suffixed artifacts; nothing maintainer-facing is renamed."""
    affiliations = {"alice": "Acme Corp", "bob": "Acme Corp", "frank": "Beta LLC", "grace": "Beta LLC"}
    _patch_pipeline(monkeypatch, tmp_path, committer_governance_config, affiliations, set(), [])

    runner.main(TEST_ORG)

    data_dir, charts_dir = tmp_path / "data", tmp_path / "charts"
    for name in (
        "maintainer_affiliations.csv",
        "committer_affiliations.csv",
        "affiliation_distribution.csv",
        "affiliation_distribution_committers.csv",
        "repo_affiliation_diversity.csv",
        "repo_affiliation_diversity_committers.csv",
    ):
        assert (data_dir / name).exists(), f"{name} not written"
    for name in ("affiliation_donut.png", "affiliation_donut_committers.png"):
        assert (charts_dir / name).exists(), f"{name} not rendered"

    committers = (data_dir / "committer_affiliations.csv").read_text(encoding="utf-8")
    assert "frank" in committers and "grace" in committers
    # bob is a maintainer on sdk-python, so he belongs to that population only.
    assert "bob" not in committers
    assert "committers" in (data_dir / "repo_affiliation_diversity_committers.csv").read_text(encoding="utf-8")


def test_main_warns_when_committer_curation_decays(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    committer_governance_config,
):
    """A thinly-curated role population is called out, not quietly charted as a small one."""
    _patch_pipeline(monkeypatch, tmp_path, committer_governance_config, {"alice": "Acme Corp"}, set(), [])

    with caplog.at_level("WARNING", logger=runner.logger.name):
        runner.main(TEST_ORG)

    warnings = [record.getMessage() for record in caplog.records if record.levelname == "WARNING"]
    assert any("curation for committer has decayed" in message for message in warnings), warnings


def test_main_stays_quiet_when_curation_is_healthy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    committer_governance_config,
):
    """A fully-curated population must not trip the decay guard."""
    affiliations = {"alice": "Acme Corp", "bob": "Acme Corp", "frank": "Beta LLC", "grace": "Beta LLC"}
    _patch_pipeline(monkeypatch, tmp_path, committer_governance_config, affiliations, set(), [])

    with caplog.at_level("WARNING", logger=runner.logger.name):
        runner.main(TEST_ORG)

    assert not [record for record in caplog.records if "decayed" in record.getMessage()]
