"""Tests for the REST-only scanners: CODEOWNERS presence and workflow-runner extraction.

These pin the deliberate error contract shared by both scanners — only a 404
counts as "absent"; any other error must propagate rather than be misreported as
a repo with no CODEOWNERS / no runners — plus the self-hosted-label heuristic.
"""

from __future__ import annotations

import base64
from unittest.mock import Mock

import pytest
import requests

from hiero_analytics.data_sources.github_rest import (
    _is_self_hosted,
    _process_workflow_file,
    fetch_repo_workflows,
    has_codeowners_file,
)


def _http_error(status_code: int) -> requests.HTTPError:
    """An HTTPError carrying a response with the given status code."""
    response = Mock()
    response.status_code = status_code
    return requests.HTTPError(response=response)


# -- has_codeowners_file: the 404-vs-error contract ---------------------------


def test_has_codeowners_true_when_a_standard_path_exists():
    """A present CODEOWNERS file at any standard location returns True."""
    client = Mock()
    client.get.return_value = {"content": "..."}
    assert has_codeowners_file(client, "org", "repo") is True


def test_has_codeowners_false_when_every_path_404s():
    """404 at every location is the only signal that means 'no CODEOWNERS'."""
    client = Mock()
    client.get.side_effect = _http_error(404)
    assert has_codeowners_file(client, "org", "repo") is False


def test_has_codeowners_propagates_non_404_errors():
    """A rate-limit / permission error must not be misread as a missing file."""
    client = Mock()
    client.get.side_effect = _http_error(403)
    with pytest.raises(requests.HTTPError):
        has_codeowners_file(client, "org", "repo")


# -- _is_self_hosted heuristic ------------------------------------------------


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("ubuntu-latest", False),  # standard GitHub-hosted
        ("self-hosted", True),  # explicitly custom
        ("${{ matrix.os }}", None),  # indeterminate expression
    ],
)
def test_is_self_hosted_classifies_labels(label, expected):
    """Standard labels -> False, custom -> True, expressions -> None (indeterminate)."""
    assert _is_self_hosted(label) is expected


# -- _process_workflow_file ---------------------------------------------------


def _workflow_payload(yaml_text: str) -> dict:
    """A contents-API payload wrapping base64 workflow YAML."""
    return {"content": base64.b64encode(yaml_text.encode()).decode()}


def test_process_workflow_file_extracts_one_record_per_job():
    """Each job with a runs-on yields a RunnerRecord tagged with its self-hosted status."""
    yaml_text = (
        "jobs:\n  build:\n    runs-on: ubuntu-latest\n  deploy:\n    name: Deploy\n    runs-on: [self-hosted, linux]\n"
    )
    client = Mock()
    client.get.return_value = _workflow_payload(yaml_text)

    records = _process_workflow_file(client, {"url": "u", "name": "ci.yml"}, "repo")

    by_job = {r.job_name: r for r in records}
    assert by_job["build"].is_self_hosted is False
    assert by_job["Deploy"].is_self_hosted is True  # any self-hosted label taints the job


def test_process_workflow_file_skips_malformed_yaml_without_raising():
    """A malformed workflow file is data, not an infra failure — skip it, return []."""
    client = Mock()
    client.get.return_value = _workflow_payload("::: not valid yaml :::\n  - [")
    assert _process_workflow_file(client, {"url": "u", "name": "bad.yml"}, "repo") == []


def test_process_workflow_file_propagates_network_errors():
    """A transport failure must surface, not be swallowed as 'no runners'."""
    client = Mock()
    client.get.side_effect = requests.ConnectionError("down")
    with pytest.raises(requests.RequestException):
        _process_workflow_file(client, {"url": "u", "name": "ci.yml"}, "repo")


# -- fetch_repo_workflows: same 404-vs-error contract as has_codeowners_file ---


def test_fetch_repo_workflows_returns_empty_on_404():
    """A repo with no .github/workflows directory (404) yields no runner records."""
    client = Mock()
    client.get.side_effect = _http_error(404)
    assert fetch_repo_workflows(client, "org", "repo") == []


def test_fetch_repo_workflows_propagates_non_404_errors():
    """A non-404 error must surface, not be misread as 'no workflows'."""
    client = Mock()
    client.get.side_effect = _http_error(500)
    with pytest.raises(requests.HTTPError):
        fetch_repo_workflows(client, "org", "repo")


def test_fetch_repo_workflows_scans_only_yaml_files():
    """Only .yml/.yaml entries are scanned; the per-file results are aggregated."""
    listing = [
        {"name": "ci.yml", "url": "u1"},
        {"name": "README.md", "url": "u2"},  # ignored — not a workflow file
    ]
    yaml_text = "jobs:\n  build:\n    runs-on: self-hosted\n"
    payload = {"content": base64.b64encode(yaml_text.encode()).decode()}

    client = Mock()
    client.get.side_effect = lambda url: listing if url.endswith("/workflows") else payload

    records = fetch_repo_workflows(client, "org", "repo")

    assert [r.workflow_file for r in records] == ["ci.yml"]
    assert records[0].is_self_hosted is True
