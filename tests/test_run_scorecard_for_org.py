"""Tests for the scorecard runner's per-repo retry behavior."""

from unittest.mock import Mock

import pytest
import requests

from hiero_analytics import run_scorecard_for_org


def _repo(name: str) -> Mock:
    repo = Mock()
    repo.name = name
    return repo


def test_fetch_all_scorecards_retries_transient_failure_once(monkeypatch):
    """A repo whose fetch fails once is retried and its record kept."""
    record = Mock()
    fetch = Mock(side_effect=[requests.ConnectionError("blip"), record])
    monkeypatch.setattr(run_scorecard_for_org, "fetch_repo_scorecard", fetch)

    result = run_scorecard_for_org.fetch_all_scorecards([_repo("repo-a")])

    assert result == [record]
    assert fetch.call_count == 2


def test_fetch_all_scorecards_raises_after_second_failure(monkeypatch):
    """Two consecutive failures propagate instead of yielding a partial chart."""
    fetch = Mock(side_effect=requests.ConnectionError("down"))
    monkeypatch.setattr(run_scorecard_for_org, "fetch_repo_scorecard", fetch)

    with pytest.raises(requests.ConnectionError):
        run_scorecard_for_org.fetch_all_scorecards([_repo("repo-a")])

    assert fetch.call_count == 2


def test_fetch_all_scorecards_skips_repos_without_scorecards(monkeypatch):
    """A None result (404 -> no scorecard) is skipped without retrying."""
    fetch = Mock(return_value=None)
    monkeypatch.setattr(run_scorecard_for_org, "fetch_repo_scorecard", fetch)

    assert run_scorecard_for_org.fetch_all_scorecards([_repo("repo-a")]) == []
    assert fetch.call_count == 1
