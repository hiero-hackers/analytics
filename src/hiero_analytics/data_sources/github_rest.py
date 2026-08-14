"""GitHub REST helpers for CODEOWNERS presence, Actions-runner classification, and dependency-graph SBOM fetching.

CODEOWNERS existence checks, workflow-YAML runner scanning, and per-repo SBOM
package lists, all via the REST API (the GraphQL ingestion lives in
``github_ingest``).
"""

from __future__ import annotations

import base64
import logging
import re
from urllib.parse import unquote

import requests
import yaml

from .github_client import GitHubClient
from .github_ingest._common import fetch_all_with_retry
from .models import DependencyManifestRecord, RunnerRecord, SbomCoverageRecord

logger = logging.getLogger(__name__)

GITHUB_HOSTED_PATTERNS = [
    r"^ubuntu-.*",
    r"^windows-.*",
    r"^macos-.*",
]

# Concurrency for fetching one repo's workflow files (small, file-count-bound).
_WORKFLOW_FETCH_WORKERS = 10

GITHUB_HOSTED_EXACT = {
    "ubuntu-latest",
    "windows-latest",
    "macos-latest",
}


def has_codeowners_file(client: GitHubClient, org: str, repo: str) -> bool:
    """Checks for the existence of a CODEOWNERS file in standard repository locations.

    Only a 404 counts as "not present"; any other error propagates so that a
    network or rate-limit failure is never reported as a missing CODEOWNERS file.
    """
    paths = [".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"]

    for path in paths:
        logger.info(f"Fetching CODEOWNERS for {repo} at {path}")

        url = f"https://api.github.com/repos/{org}/{repo}/contents/{path}"
        try:
            response = client.get(url)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                continue
            raise

        if response:
            return True

    return False


def _parse_purl(purl: str) -> tuple[str, str, str | None] | None:
    """Parse a package URL (purl) into (ecosystem, name, version).

    Format: ``pkg:type/namespace/name@version`` or ``pkg:type/name@version``
    (namespace optional; npm scopes and Maven groupIds arrive as the
    namespace segment, percent-encoded per the purl spec — e.g. an npm scope
    is ``%40scope``, not ``@scope``). Qualifiers (``?...``) and subpath
    (``#...``) are dropped — irrelevant for repo resolution. Returns
    ``None`` for anything that doesn't parse as ``pkg:...`` rather than
    raising, since a single malformed purl shouldn't fail the whole repo's
    SBOM.
    """
    if not purl.startswith("pkg:"):
        return None
    body = purl[len("pkg:") :].split("?", 1)[0].split("#", 1)[0]
    if "/" not in body:
        return None
    ecosystem, rest = body.split("/", 1)
    name_and_version, _, version = rest.rpartition("@")
    if not name_and_version:
        # No '@version' segment at all -- treat the whole remainder as the name.
        name_and_version, version = rest, None
    return ecosystem.lower(), unquote(name_and_version), unquote(version) if version else None


def fetch_repo_sbom(
    client: GitHubClient, org: str, repo: str
) -> tuple[SbomCoverageRecord, list[DependencyManifestRecord]]:
    """Fetch and parse one repo's dependency-graph SBOM.

    Only a 404 or 403 counts as "dependency graph disabled" (status
    ``"disabled"``, empty package list) — mirroring ``has_codeowners_file``'s
    exact treatment, since GitHub returns 404/403 for repos where the
    dependency graph feature is off, not for genuine failures. Any other
    error propagates as status ``"error"`` with the repo's coverage row
    still returned (never silently dropped), so a network/permission issue
    reads as "we don't know," not "this repo has no dependencies."

    NOTE: package parsing is based on the documented SPDX/purl shape of the
    dependency-graph SBOM endpoint; verify against a real response before
    relying on this for production coverage numbers — see the design note
    on #338.
    """
    url = f"https://api.github.com/repos/{org}/{repo}/dependency-graph/sbom"
    try:
        payload = client.get(url)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in (403, 404):
            logger.debug("Dependency graph disabled for %s", repo)
            return SbomCoverageRecord(repo=repo, status="disabled", package_count=0), []
        logger.error("SBOM fetch failed for %s: %s", repo, exc)
        return SbomCoverageRecord(repo=repo, status="error", package_count=0), []
    except requests.RequestException as exc:
        logger.error("SBOM fetch failed for %s: %s", repo, exc)
        return SbomCoverageRecord(repo=repo, status="error", package_count=0), []

    sbom = (payload or {}).get("sbom") or {}
    packages = sbom.get("packages") or []
    # The document's own "described" package(s) represent the repo itself,
    # not a dependency -- exclude by SPDXID via the SPDX-standard
    # documentDescribes list rather than guessing from the name.
    described_ids = set(sbom.get("documentDescribes") or [])

    records: list[DependencyManifestRecord] = []
    for pkg in packages:
        if not isinstance(pkg, dict) or pkg.get("SPDXID") in described_ids:
            continue
        purls = [
            ref.get("referenceLocator", "")
            for ref in (pkg.get("externalRefs") or [])
            if isinstance(ref, dict) and ref.get("referenceType") == "purl"
        ]
        parsed = next((p for purl in purls if (p := _parse_purl(purl)) is not None), None)
        if parsed is None:
            continue
        ecosystem, package_name, version = parsed
        records.append(
            DependencyManifestRecord(repo=repo, package_name=package_name, ecosystem=ecosystem, version=version)
        )

    return SbomCoverageRecord(repo=repo, status="ok", package_count=len(records)), records


def _is_self_hosted(label: str) -> bool | None:
    """
    Determines if a runner is self-hosted.

    Returns:
        True: Explicitly a custom/self-hosted runner.
        False: Explicitly a standard GitHub-hosted runner.
        None: Indeterminate (complex expressions/matrix variables).
    """
    label_value = str(label).lower().strip()

    if label_value in GITHUB_HOSTED_EXACT or any(re.match(p, label_value) for p in GITHUB_HOSTED_PATTERNS):
        return False

    if "${{" in label_value:
        return None

    return True


def _process_workflow_file(client: GitHubClient, wf: dict, repo: str) -> list[RunnerRecord]:
    """Process a single yml file and extract job/runner records."""
    results: list[RunnerRecord] = []
    try:
        resp = client.get(wf["url"])
        if not (resp and "content" in resp):
            return []

        raw = base64.b64decode(resp["content"]).decode("utf-8")
        data = yaml.safe_load(raw)

        jobs = data.get("jobs", {})
        if not isinstance(jobs, dict):
            return []

        for job_id, job_cfg in jobs.items():
            if not isinstance(job_cfg, dict):
                continue

            job_name = job_cfg.get("name", job_id)
            runs_on = job_cfg.get("runs-on")
            if not runs_on:
                continue

            labels = [runs_on] if isinstance(runs_on, (str, int)) else runs_on

            final_status = False

            for label_value in labels:
                status = _is_self_hosted(str(label_value))

                if status is True:
                    final_status = True
                    break
                if status is None:
                    final_status = None

            results.append(
                RunnerRecord(
                    repo=repo,
                    workflow_file=wf["name"],
                    job_name=job_name,
                    runner=str(runs_on),
                    is_self_hosted=final_status,
                )
            )
    except requests.RequestException:
        raise  # network/API failures must not read as "no runners in this file"
    except Exception as e:
        # A malformed workflow file is data, not an infrastructure failure —
        # skip it loudly rather than failing the whole repo scan.
        logger.error(f"Failed to parse {wf['name']}: {e}")

    return results


def fetch_repo_workflows(client: GitHubClient, org: str, repo: str) -> list[RunnerRecord]:
    """Fetch per-job runner records for a repository's workflow files.

    Only a 404 counts as "no workflow directory"; any other error propagates so
    a transient/network/permission failure is never misreported as a repo with
    no runners.
    """
    url = f"https://api.github.com/repos/{org}/{repo}/contents/.github/workflows"
    try:
        workflows = client.get(url)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            logger.debug("No workflow directory in %s", repo)
            return []
        raise

    if not isinstance(workflows, list):
        return []

    yaml_files = [wf for wf in workflows if wf["name"].endswith((".yml", ".yaml"))]

    # The shared fan-out retries transient failures once and raises
    # PartialOrgFetchError rather than returning a silently partial scan.
    return fetch_all_with_retry(
        yaml_files,
        _WORKFLOW_FETCH_WORKERS,
        lambda wf: _process_workflow_file(client, wf, repo),
        task_desc=f"workflow files ({repo})",
        describe=lambda wf: str(wf.get("name", "?")),
    )


# Concurrency for the org-wide SBOM fan-out (one call per repo).
_SBOM_FETCH_WORKERS = 8


def fetch_org_sbom_data(
    client: GitHubClient,
    org: str,
    repo_names: list[str],
    max_workers: int = _SBOM_FETCH_WORKERS,
) -> tuple[list[SbomCoverageRecord], list[DependencyManifestRecord]]:
    """Fetch SBOM coverage + packages for every repo in ``repo_names``.

    Returns ``(coverage, packages)`` — always exactly one coverage row per
    input repo (``fetch_repo_sbom`` never raises; disabled/error states are
    returned, not thrown), and zero or more package rows per repo.

    ``fetch_all_with_retry`` expects a flat per-item list, so each repo's
    ``(coverage, packages)`` pair is flattened into one list (coverage row
    first) and split back apart here by type after the fan-out completes —
    simpler than teaching the shared retry helper a second return shape for
    one caller.
    """

    def per_repo(repo: str) -> list[SbomCoverageRecord | DependencyManifestRecord]:
        coverage, packages = fetch_repo_sbom(client, org, repo)
        return [coverage, *packages]

    combined = fetch_all_with_retry(
        repo_names,
        max_workers,
        per_repo,
        task_desc="SBOM data",
        describe=str,
    )
    coverage = [r for r in combined if isinstance(r, SbomCoverageRecord)]
    packages = [r for r in combined if isinstance(r, DependencyManifestRecord)]
    return coverage, packages
