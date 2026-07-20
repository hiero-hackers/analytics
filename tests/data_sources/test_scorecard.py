"""Tests for the scorecard data source module."""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest
import requests

from hiero_analytics.data_sources.models import ScorecardRecord
from hiero_analytics.data_sources.scorecard import fetch_repo_scorecard

MOCK_RESPONSE = {
    "score": 7.5,
    "date": "2026-04-01T00:00:00Z",
    "checks": [
        {"name": "Maintained", "score": 10},
        {"name": "Code-Review", "score": 8},
    ],
}


@patch("hiero_analytics.data_sources.scorecard.requests.get")
def test_fetch_repo_scorecard_success(mock_get):
    """Test that fetch_scorecard can return a ScorecardRecord."""
    mock_response = Mock()
    mock_response.json.return_value = MOCK_RESPONSE
    mock_response.raise_for_status.return_value = None

    mock_get.return_value = mock_response

    repo = "hiero-sdk-python"
    record = fetch_repo_scorecard(repo)

    assert record is not None
    assert isinstance(record, ScorecardRecord)

    assert record.repo == repo
    assert record.score == 7.5

    assert "Maintained" in record.checks
    assert record.checks["Maintained"] == 10

    assert isinstance(record.date, datetime)
    assert record.date.year == 2026


@patch("hiero_analytics.data_sources.scorecard.requests.get")
def test_fetch_repo_scorecard_not_found(mock_get):
    """Test that fetch_scorecard return None when scorecard not found."""
    mock_response = Mock()
    mock_response.raise_for_status.side_effect = Exception()
    mock_response.status_code = 404

    mock_get.side_effect = requests.exceptions.HTTPError(response=mock_response)

    # unknown repo or repo with no open-ssf set
    repo = "unknown-repo"
    record = fetch_repo_scorecard(repo)

    assert record is None


@patch("hiero_analytics.data_sources.scorecard.requests.get")
def test_fetch_repo_scorecard_network_error_raises(mock_get):
    """A network failure propagates instead of masquerading as a missing scorecard."""
    mock_get.side_effect = requests.exceptions.RequestException()

    with pytest.raises(requests.exceptions.RequestException):
        fetch_repo_scorecard("hiero-sdk-python")


@patch("hiero_analytics.data_sources.scorecard.requests.get")
def test_fetch_repo_scorecard_server_error_raises(mock_get):
    """A non-404 HTTP error propagates instead of masquerading as a missing scorecard."""
    mock_response = Mock()
    mock_response.status_code = 500

    mock_get.side_effect = requests.exceptions.HTTPError(response=mock_response)

    with pytest.raises(requests.exceptions.HTTPError):
        fetch_repo_scorecard("hiero-sdk-python")
