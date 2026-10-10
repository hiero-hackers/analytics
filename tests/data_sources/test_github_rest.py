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


# -- fetch_repo_sbom: the 404-vs-error contract, and SBOM parsing ------------


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


def test_fetch_repo_sbom_treats_404_as_disabled():
    """404 is the only unambiguous 'dependency graph off for this repo' signal."""
    client = Mock()
    client.get.side_effect = _http_error(404)

    coverage, records = fetch_repo_sbom(client, "org", "repo")

    assert coverage == SbomCoverageRecord(repo="repo", status="disabled", package_count=0)
    assert records == []


@pytest.mark.parametrize("status_code", [403, 500])
def test_fetch_repo_sbom_propagates_http_errors(status_code):
    """HTTP failures must propagate so the org-level retry can handle them."""
    client = Mock()
    client.get.side_effect = _http_error(status_code)

    with pytest.raises(requests.HTTPError):
        fetch_repo_sbom(client, "org", "repo")


@pytest.mark.parametrize("malformed_sbom", [{"sbom": "not-an-object"}, {"sbom": None}, "not-an-object", None])
def test_fetch_repo_sbom_reports_error_when_sbom_is_not_an_object(malformed_sbom):
    """A malformed payload/sbom must not be reported as an available SBOM with zero packages."""
    client = Mock()
    client.get.return_value = malformed_sbom

    coverage, records = fetch_repo_sbom(client, "org", "repo")

    assert coverage == SbomCoverageRecord(repo="repo", status="error", package_count=0)
    assert records == []


@pytest.mark.parametrize("malformed_packages", [{"not": "a list"}, "not-a-list", 5])
def test_fetch_repo_sbom_reports_error_when_packages_is_not_a_list(malformed_packages):
    """'packages' present but the wrong type must not silently resolve to an empty manifest."""
    client = Mock()
    client.get.return_value = {"sbom": {"documentDescribes": [], "packages": malformed_packages}}

    coverage, records = fetch_repo_sbom(client, "org", "repo")

    assert coverage == SbomCoverageRecord(repo="repo", status="error", package_count=0)
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


def test_fetch_org_sbom_data_retries_http_failures():
    """HTTP failures from a repo fetch reach the org-level retry mechanism."""
    calls = {"repo-a": 0}

    def fake_get(url):
        if "repo-a" in url:
            calls["repo-a"] += 1

            if calls["repo-a"] == 1:
                raise _http_error(500)

            return {
                "sbom": {
                    "documentDescribes": [],
                    "packages": [
                        {
                            "SPDXID": "x",
                            "externalRefs": [
                                {
                                    "referenceType": "purl",
                                    "referenceLocator": "pkg:npm/left-pad@1.0.0",
                                }
                            ],
                        }
                    ],
                }
            }

        raise _http_error(404)

    client = Mock()
    client.get.side_effect = fake_get

    coverage, packages = fetch_org_sbom_data(
        client,
        "org",
        ["repo-a", "repo-b"],
        max_workers=1,
    )

    assert calls["repo-a"] == 2
    assert {c.repo: c.status for c in coverage} == {
        "repo-a": "ok",
        "repo-b": "disabled",
    }
    assert len(packages) == 1


# -- SBOM TTL caching ----------------------------------------------------------


def _sbom_payload(*purls: str) -> dict:
    return {
        "sbom": {
            "documentDescribes": [],
            "packages": [
                {"SPDXID": f"p{i}", "externalRefs": [{"referenceType": "purl", "referenceLocator": purl}]}
                for i, purl in enumerate(purls)
            ],
        }
    }


def test_fetch_repo_sbom_cache_hit_skips_the_request():
    """A second call within the TTL is served from cache with identical output."""
    client = Mock()
    client.get.return_value = _sbom_payload("pkg:npm/left-pad@1.0.0")

    first = fetch_repo_sbom(client, "org", "repo")
    second = fetch_repo_sbom(client, "org", "repo")

    assert client.get.call_count == 1
    assert second == first
    assert second[0] == SbomCoverageRecord(repo="repo", status="ok", package_count=1)


def test_fetch_repo_sbom_cache_hit_preserves_empty_manifest():
    """An ok SBOM with zero packages is a valid cached result, not a miss."""
    client = Mock()
    client.get.return_value = _sbom_payload()

    fetch_repo_sbom(client, "org", "repo")
    coverage, records = fetch_repo_sbom(client, "org", "repo")

    assert client.get.call_count == 1
    assert coverage == SbomCoverageRecord(repo="repo", status="ok", package_count=0)
    assert records == []


def test_fetch_repo_sbom_cache_miss_fetches_and_scopes_by_org_and_repo():
    """Different repos/orgs never share a cache entry."""
    client = Mock()
    client.get.return_value = _sbom_payload("pkg:npm/left-pad@1.0.0")

    fetch_repo_sbom(client, "org", "repo-a")
    fetch_repo_sbom(client, "org", "repo-b")
    fetch_repo_sbom(client, "other-org", "repo-a")

    assert client.get.call_count == 3


def test_fetch_repo_sbom_expired_entry_is_refetched(monkeypatch):
    """An entry older than the TTL is treated as a miss and replaced with fresh data."""
    from datetime import UTC, datetime, timedelta

    import hiero_analytics.data_sources.cache as cache

    client = Mock()
    client.get.side_effect = [
        _sbom_payload("pkg:npm/left-pad@1.0.0"),
        _sbom_payload("pkg:npm/left-pad@2.0.0"),
    ]

    fetch_repo_sbom(client, "org", "repo", cache_ttl_seconds=60)

    real_datetime = datetime

    class _Later(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime.now(tz) + timedelta(seconds=120)

    monkeypatch.setattr(cache, "datetime", _Later)
    assert UTC  # keep import used
    _, records = fetch_repo_sbom(client, "org", "repo", cache_ttl_seconds=60)

    assert client.get.call_count == 2
    assert [r.version for r in records] == ["2.0.0"]


def test_fetch_repo_sbom_refresh_bypasses_cache():
    """refresh=True forces a re-fetch even when a fresh entry exists."""
    client = Mock()
    client.get.return_value = _sbom_payload("pkg:npm/left-pad@1.0.0")

    fetch_repo_sbom(client, "org", "repo")
    fetch_repo_sbom(client, "org", "repo", refresh=True)

    assert client.get.call_count == 2


def test_fetch_repo_sbom_use_cache_false_never_reads_or_writes():
    """Disabling the cache always hits GitHub and leaves nothing behind."""
    client = Mock()
    client.get.return_value = _sbom_payload("pkg:npm/left-pad@1.0.0")

    fetch_repo_sbom(client, "org", "repo", use_cache=False)
    fetch_repo_sbom(client, "org", "repo", use_cache=False)
    fetch_repo_sbom(client, "org", "repo")  # default cache on: nothing was written above

    assert client.get.call_count == 3


def test_fetch_repo_sbom_does_not_cache_disabled_results():
    """A 404 is not cached, so enabling the dependency graph is noticed on the next run."""
    client = Mock()
    client.get.side_effect = [_http_error(404), _sbom_payload("pkg:npm/left-pad@1.0.0")]

    first_coverage, _ = fetch_repo_sbom(client, "org", "repo")
    second_coverage, _ = fetch_repo_sbom(client, "org", "repo")

    assert first_coverage.status == "disabled"
    assert second_coverage.status == "ok"
    assert client.get.call_count == 2


@pytest.mark.parametrize("malformed", [{"sbom": None}, {"sbom": {"packages": "nope"}}, None])
def test_fetch_repo_sbom_does_not_cache_malformed_responses(malformed):
    """Malformed payloads are reported as errors and never stored as valid SBOM data."""
    client = Mock()
    client.get.side_effect = [malformed, _sbom_payload("pkg:npm/left-pad@1.0.0")]

    first_coverage, _ = fetch_repo_sbom(client, "org", "repo")
    second_coverage, _ = fetch_repo_sbom(client, "org", "repo")

    assert first_coverage.status == "error"
    assert second_coverage.status == "ok"
    assert client.get.call_count == 2


def test_fetch_repo_sbom_does_not_cache_propagated_http_errors():
    """A failed request writes nothing; the next call fetches again."""
    client = Mock()
    client.get.side_effect = [_http_error(500), _sbom_payload("pkg:npm/left-pad@1.0.0")]

    with pytest.raises(requests.HTTPError):
        fetch_repo_sbom(client, "org", "repo")
    coverage, _ = fetch_repo_sbom(client, "org", "repo")

    assert coverage.status == "ok"
    assert client.get.call_count == 2


def test_fetch_org_sbom_data_only_refetches_uncached_repos():
    """On a re-run, cached repos are served locally and only the rest hit GitHub."""
    calls: list[str] = []

    def fake_get(url):
        calls.append(url)
        if "repo-a" in url:
            return _sbom_payload("pkg:npm/left-pad@1.0.0")
        raise _http_error(404)

    client = Mock()
    client.get.side_effect = fake_get

    first = fetch_org_sbom_data(client, "org", ["repo-a", "repo-b"], max_workers=2)
    calls.clear()
    second = fetch_org_sbom_data(client, "org", ["repo-a", "repo-b"], max_workers=2)

    assert [u for u in calls if "repo-a" in u] == []  # repo-a served from cache
    assert len([u for u in calls if "repo-b" in u]) == 1  # 404s are not cached
    assert sorted(second[0], key=lambda c: c.repo) == sorted(first[0], key=lambda c: c.repo)
    assert second[1] == first[1]
