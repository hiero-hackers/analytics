"""Tests for the scorecard runner: per-repo retry behavior and the tables it writes."""

from datetime import UTC, datetime
from unittest.mock import Mock

import pandas as pd
import pytest
import requests

from hiero_analytics.data_sources.models import ScorecardRecord
from hiero_analytics.pipelines import scorecard


def _repo(name: str) -> Mock:
    repo = Mock()
    repo.name = name
    return repo


def test_fetch_all_scorecards_retries_transient_failure_once(monkeypatch):
    """A repo whose fetch fails once is retried and its record kept."""
    record = Mock()
    fetch = Mock(side_effect=[requests.ConnectionError("blip"), record])
    monkeypatch.setattr(scorecard, "fetch_repo_scorecard", fetch)

    result = scorecard.fetch_all_scorecards([_repo("repo-a")])

    assert result == [record]
    assert fetch.call_count == 2


def test_fetch_all_scorecards_raises_after_second_failure(monkeypatch):
    """Two consecutive failures propagate instead of yielding a partial chart."""
    fetch = Mock(side_effect=requests.ConnectionError("down"))
    monkeypatch.setattr(scorecard, "fetch_repo_scorecard", fetch)

    with pytest.raises(requests.ConnectionError):
        scorecard.fetch_all_scorecards([_repo("repo-a")])

    assert fetch.call_count == 2


def test_fetch_all_scorecards_skips_repos_without_scorecards(monkeypatch):
    """A None result (404 -> no scorecard) is skipped without retrying."""
    fetch = Mock(return_value=None)
    monkeypatch.setattr(scorecard, "fetch_repo_scorecard", fetch)

    assert scorecard.fetch_all_scorecards([_repo("repo-a")]) == []
    assert fetch.call_count == 1


def _scorecard(repo: str, score: float, checks: dict[str, int]) -> ScorecardRecord:
    return ScorecardRecord(repo=repo, score=score, checks=checks, date=datetime(2026, 7, 1, tzinfo=UTC))


def test_main_writes_the_score_and_check_tables(monkeypatch, stub_pipeline_context):
    """Both tables land with sidecars; an unreported check stays blank, never a zero."""
    _client, data_dir = stub_pipeline_context(scorecard)
    monkeypatch.setattr(scorecard, "fetch_org_repos", lambda _client, _org: [_repo("a"), _repo("b")])
    monkeypatch.setattr(
        scorecard,
        "fetch_all_scorecards",
        lambda _repos, org: [  # noqa: ARG005  (keyword the pipeline passes)
            _scorecard("a", 7.5, {"Maintained": 10, "Code-Review": 4}),
            _scorecard("b", 3.0, {"Maintained": 2}),
        ],
    )

    scorecard.main("test-org")

    for name in ("org_scorecard.csv", "org_scorecard_checks.csv"):
        assert (data_dir / name).exists(), name
        assert (data_dir / f"{name}.meta.json").exists(), name
    scores = pd.read_csv(data_dir / "org_scorecard.csv")
    assert sorted(scores["repo"]) == ["a", "b"]
    checks = pd.read_csv(data_dir / "org_scorecard_checks.csv").set_index("repo")
    assert len(checks) == 2
    assert checks.loc["a", "Code-Review"] == 4
    assert pd.isna(checks.loc["b", "Code-Review"])


@pytest.mark.parametrize("repos", [[], [None]])
def test_main_writes_nothing_without_repos_or_scorecards(monkeypatch, stub_pipeline_context, repos):
    """No repositories, or repositories without a scorecard, leave no tables behind."""
    _client, data_dir = stub_pipeline_context(scorecard)
    monkeypatch.setattr(scorecard, "fetch_org_repos", lambda _client, _org: [_repo("a")] if repos else [])
    monkeypatch.setattr(scorecard, "fetch_all_scorecards", lambda _repos, org: [])  # noqa: ARG005

    scorecard.main("test-org")

    assert not list(data_dir.glob("*.csv"))
