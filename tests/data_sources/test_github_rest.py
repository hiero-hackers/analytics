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
    _parse_purl,
    _process_workflow_file,
    fetch_org_sbom_data,
    fetch_repo_sbom,
    fetch_repo_workflows,
    has_codeowners_file,
)
from hiero_analytics.data_sources.models import DependencyManifestRecord, SbomCoverageRecord


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


# -- _parse_purl --------------------------------------------------------------


@pytest.mark.parametrize(
    ("purl", "expected"),
    [
        ("pkg:npm/left-pad@1.0.1", ("npm", "left-pad", "1.0.1")),
        ("pkg:npm/%40scope/pkg@2.0.0", ("npm", "@scope/pkg", "2.0.0")),
        ("pkg:maven/com.example/thing@2.0", ("maven", "com.example/thing", "2.0")),
        ("pkg:pypi/requests@2.31.0", ("pypi", "requests", "2.31.0")),
        ("pkg:cargo/serde@1.0.0?extra=1", ("cargo", "serde", "1.0.0")),  # qualifiers dropped
        ("pkg:golang/github.com/org/mod@v1.2.3", ("golang", "github.com/org/mod", "v1.2.3")),
        ("pkg:npm/no-version", ("npm", "no-version", None)),  # no '@version' segment at all
    ],
)
def test_parse_purl_handles_each_ecosystem_shape(purl, expected):
    """Each ecosystem's purl shape parses to (ecosystem, name, version), scope/groupId decoded."""
    assert _parse_purl(purl) == expected


@pytest.mark.parametrize("malformed", ["not-a-purl", "pkg:", "pkg:npm-no-slash"])
def test_parse_purl_returns_none_for_malformed_input(malformed):
    """Malformed input returns None rather than raising -- one bad purl shouldn't fail a repo's SBOM."""
    assert _parse_purl(malformed) is None


# -- fetch_repo_sbom: the 404/403-vs-error contract, and SBOM parsing ---------


def test_fetch_repo_sbom_parses_packages_and_excludes_the_described_root():
    """Packages parse to DependencyManifestRecord; the repo's own root package is excluded."""
    client = Mock()
    client.get.return_value = {
        "sbom": {
            "documentDescribes": ["SPDXRef-root"],
            "packages": [
                {"SPDXID": "SPDXRef-root", "name": "org/repo"},  # the repo itself -- must be excluded
                {
                    "SPDXID": "SPDXRef-1",
                    "name": "lodash",
                    "externalRefs": [{"referenceType": "purl", "referenceLocator": "pkg:npm/lodash@4.17.21"}],
                },
            ],
        }
    }

    coverage, records = fetch_repo_sbom(client, "org", "repo")

    assert coverage == SbomCoverageRecord(repo="repo", status="ok", package_count=1)
    assert records == [DependencyManifestRecord(repo="repo", package_name="lodash", ecosystem="npm", version="4.17.21")]


def test_fetch_repo_sbom_skips_packages_without_a_parseable_purl():
    """A package with no purl external ref is skipped, not fabricated from the raw name."""
    client = Mock()
    client.get.return_value = {
        "sbom": {
            "documentDescribes": [],
            "packages": [{"SPDXID": "SPDXRef-1", "name": "mystery-pkg", "externalRefs": []}],
        }
    }

    coverage, records = fetch_repo_sbom(client, "org", "repo")

    assert records == []
    assert coverage.status == "ok"
    assert coverage.package_count == 0


@pytest.mark.parametrize("status_code", [403, 404])
def test_fetch_repo_sbom_treats_403_and_404_as_disabled(status_code):
    """Both 403 and 404 mean 'dependency graph off for this repo', not an error."""
    client = Mock()
    client.get.side_effect = _http_error(status_code)

    coverage, records = fetch_repo_sbom(client, "org", "repo")

    assert coverage == SbomCoverageRecord(repo="repo", status="disabled", package_count=0)
    assert records == []


def test_fetch_repo_sbom_reports_other_errors_as_error_status_not_disabled():
    """A genuine failure (5xx, auth, etc.) is status='error', distinguishable from 'disabled'."""
    client = Mock()
    client.get.side_effect = _http_error(500)

    coverage, records = fetch_repo_sbom(client, "org", "repo")

    assert coverage.status == "error"
    assert records == []


# -- fetch_org_sbom_data: the org-wide fan-out --------------------------------


def test_fetch_org_sbom_data_returns_one_coverage_row_per_repo():
    """Every input repo gets exactly one coverage row, regardless of outcome."""

    def fake_get(url):
        if "repo-a" in url:
            return {
                "sbom": {
                    "documentDescribes": [],
                    "packages": [
                        {
                            "SPDXID": "x",
                            "externalRefs": [{"referenceType": "purl", "referenceLocator": "pkg:npm/left-pad@1.0.0"}],
                        }
                    ],
                }
            }
        raise _http_error(404)

    client = Mock()
    client.get.side_effect = fake_get

    coverage, packages = fetch_org_sbom_data(client, "org", ["repo-a", "repo-b"], max_workers=2)

    assert {c.repo for c in coverage} == {"repo-a", "repo-b"}
    assert {c.repo: c.status for c in coverage} == {"repo-a": "ok", "repo-b": "disabled"}
    assert [p.repo for p in packages] == ["repo-a"]
