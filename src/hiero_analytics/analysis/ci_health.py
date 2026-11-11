"""Security checks for GitHub Actions workflow files."""

from __future__ import annotations

import re
from typing import NamedTuple

import yaml

from hiero_analytics.analysis.ci_health_types import CheckResult

USES_PATTERN = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.MULTILINE)
PERMISSIONS_PATTERN = re.compile(r"^\s*permissions\s*:", re.MULTILINE)


def extract_action_references(workflow_text: str) -> list[str]:
    """Extract GitHub Actions `uses:` references from workflow YAML."""
    return USES_PATTERN.findall(workflow_text)


def is_sha_pinned(reference: str) -> bool:
    """Return whether an Actions reference is pinned to an immutable revision."""
    if reference.startswith("$/"):
        return True
    if reference.startswith("docker://"):
        _, _, digest = reference.rpartition("@")
        return bool(re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest))
    _, _, ref = reference.rpartition("@")
    return bool(re.fullmatch(r"[0-9a-fA-F]{40}", ref))


def find_unpinned_actions(workflow_text: str) -> list[str]:
    """Return GitHub Actions references that are not pinned to a commit SHA."""
    return [reference for reference in extract_action_references(workflow_text) if not is_sha_pinned(reference)]


def find_unpinned_actions_with_lines(
    workflow_text: str,
) -> list[tuple[str, int]]:
    """Return unpinned GitHub Actions references with their line numbers."""
    findings: list[tuple[str, int]] = []

    for line_number, line in enumerate(workflow_text.splitlines(), start=1):
        match = USES_PATTERN.match(line)
        if match:
            reference = match.group(1)
            if not is_sha_pinned(reference):
                findings.append((reference, line_number))

    return findings


def find_permissions_with_lines(workflow_text: str) -> list[int]:
    """Return line numbers where `permissions:` is explicitly declared."""
    lines: list[int] = []

    for line_number, line in enumerate(workflow_text.splitlines(), start=1):
        if PERMISSIONS_PATTERN.match(line):
            lines.append(line_number)

    return lines


def has_explicit_permissions(workflow_text: str) -> bool:
    """Return whether a workflow has effective explicit permissions coverage."""
    try:
        workflow = yaml.safe_load(workflow_text)
    except yaml.YAMLError:
        return False

    if not isinstance(workflow, dict):
        return False

    if "permissions" in workflow:
        return True

    jobs = workflow.get("jobs")

    if not isinstance(jobs, dict) or not jobs:
        return False

    return all(isinstance(job, dict) and "permissions" in job for job in jobs.values())


def check_actions_sha_pinned(
    workflows: list[dict[str, str]],
) -> CheckResult:
    """Check whether GitHub Actions references are pinned to commit SHAs."""
    if not workflows:
        return CheckResult(
            check="actions_sha_pinned",
            band="actions",
            status="na",
            evidence="Repository has no GitHub Actions workflows.",
            location="",
        )

    unpinned_actions: list[str] = []
    locations: list[str] = []

    for workflow in workflows:
        findings = find_unpinned_actions_with_lines(workflow["text"])

        for reference, line_number in findings:
            unpinned_actions.append(reference)
            locations.append(f".github/workflows/{workflow['name']}:{line_number}")

    if not unpinned_actions:
        return CheckResult(
            check="actions_sha_pinned",
            band="actions",
            status="pass",
            evidence="All GitHub Actions are pinned to full commit SHAs.",
            location="",
        )

    return CheckResult(
        check="actions_sha_pinned",
        band="actions",
        status="fail",
        evidence=(
            f"Found {len(unpinned_actions)} GitHub Actions reference(s) "
            "that are not pinned to a full commit SHA: " + ", ".join(unpinned_actions)
        ),
        location="; ".join(locations),
    )


def check_explicit_permissions(
    workflows: list[dict[str, str]],
) -> CheckResult:
    """Check whether each workflow has explicit permissions coverage."""
    if not workflows:
        return CheckResult(
            check="explicit_permissions",
            band="permissions",
            status="na",
            evidence="Repository has no GitHub Actions workflows.",
            location="",
        )

    missing_permissions: list[str] = []
    locations: list[str] = []

    for workflow in workflows:
        workflow_name = workflow["name"]
        workflow_text = workflow["text"]
        permission_lines = find_permissions_with_lines(workflow_text)

        if not has_explicit_permissions(workflow_text):
            missing_permissions.append(workflow_name)

            if permission_lines:
                locations.extend(f".github/workflows/{workflow_name}:{line_number}" for line_number in permission_lines)
            else:
                locations.append(f".github/workflows/{workflow_name}")

            continue

        locations.extend(f".github/workflows/{workflow_name}:{line_number}" for line_number in permission_lines)

    if not missing_permissions:
        return CheckResult(
            check="explicit_permissions",
            band="permissions",
            status="pass",
            evidence=(f"All {len(workflows)} workflow(s) have explicit GitHub Actions permissions coverage."),
            location="; ".join(locations),
        )

    return CheckResult(
        check="explicit_permissions",
        band="permissions",
        status="fail",
        evidence=(
            f"Found {len(missing_permissions)} workflow(s) without "
            "complete explicit permissions coverage: " + ", ".join(missing_permissions)
        ),
        location="; ".join(locations),
    )


DCO_PATTERNS = (
    "dco",
    "developer certificate of origin",
    "developercertificateoforigin",
)

CODEQL_PATTERNS = (
    "codeql",
    "github/codeql-action",
)


def strip_yaml_comments(text: str) -> str:
    """Remove YAML comments while preserving hash characters in quoted values."""
    lines: list[str] = []

    for line in text.splitlines():
        quote: str | None = None
        output: list[str] = []

        for index, char in enumerate(line):
            if char in {"'", '"'}:
                if quote is None:
                    quote = char
                elif quote == char:
                    quote = None
            elif char == "#" and quote is None and (index == 0 or line[index - 1].isspace()):
                break

            output.append(char)

        lines.append("".join(output))

    return "\n".join(lines)


def find_workflow_names_containing(
    workflows: list[dict[str, str]],
    patterns: tuple[str, ...],
) -> list[str]:
    """Return workflow names whose names or contents match known patterns."""
    matches: list[str] = []

    for workflow in workflows:
        name = workflow["name"]
        text = strip_yaml_comments(workflow["text"]).lower()

        if any(pattern in name.lower() or pattern in text for pattern in patterns):
            matches.append(name)

    return matches


def check_repository_security_configuration(
    workflows: list[dict[str, str]],
    *,
    has_wiki_enabled: bool,
    has_issues_enabled: bool,
    has_discussions_enabled: bool,
    has_projects_enabled: bool,
    web_commit_signoff_required: bool,
) -> CheckResult:
    """Check repository security-related settings and workflow controls."""
    dco_workflows = find_workflow_names_containing(
        workflows,
        DCO_PATTERNS,
    )
    codeql_workflows = find_workflow_names_containing(
        workflows,
        CODEQL_PATTERNS,
    )

    settings = (
        f"wiki={has_wiki_enabled}, "
        f"issues={has_issues_enabled}, "
        f"discussions={has_discussions_enabled}, "
        f"projects={has_projects_enabled}, "
        f"web_commit_signoff_required={web_commit_signoff_required}"
    )

    controls: list[str] = []
    locations: list[str] = []

    if web_commit_signoff_required:
        controls.append("web commit sign-off enabled")
    else:
        controls.append("web commit sign-off disabled")
        locations.append("repository settings")

    if dco_workflows:
        controls.append("DCO workflow detected: " + ", ".join(dco_workflows))
        locations.extend(f".github/workflows/{name}" for name in dco_workflows)
    else:
        controls.append("DCO workflow not detected")

    if codeql_workflows:
        controls.append("CodeQL workflow detected: " + ", ".join(codeql_workflows))
        locations.extend(f".github/workflows/{name}" for name in codeql_workflows)
    else:
        controls.append("CodeQL workflow not detected")

    if not web_commit_signoff_required:
        status = "fail"
    elif not dco_workflows or not codeql_workflows:
        status = "review"
    else:
        status = "pass"

    return CheckResult(
        check="repository_security_configuration",
        band="repository",
        status=status,
        evidence=(settings + ". " + "; ".join(controls) + "."),
        location="; ".join(locations),
    )


class DockerfileFinding(NamedTuple):
    """Classified external base-image reference from a Dockerfile."""

    reference: str
    classification: str  # "pinned", "unpinned", or "unresolved"
    line_number: int


def _get_dockerfile_logical_lines(dockerfile_text: str) -> list[tuple[str, int]]:
    r"""Join backslash line continuations into logical instructions with 1-based start line.

    Note: The '# escape=' parser directive is not supported. Backslash ('\') is always
    treated as the line continuation character.
    """
    logical_lines: list[tuple[str, int]] = []
    current_parts: list[str] = []
    start_line: int | None = None

    for line_number, raw_line in enumerate(dockerfile_text.splitlines(), start=1):
        line = raw_line.strip()
        if start_line is None:
            if not line or line.startswith("#"):
                continue
            start_line = line_number

        if line.endswith("\\"):
            current_parts.append(line[:-1].rstrip())
        else:
            current_parts.append(line)
            logical_lines.append((" ".join(current_parts), start_line))
            current_parts = []
            start_line = None

    if current_parts and start_line is not None:
        logical_lines.append((" ".join(current_parts), start_line))

    return logical_lines


def find_dockerfile_base_images_with_lines(
    dockerfile_text: str,
) -> list[DockerfileFinding]:
    r"""Extract classified external base-image references with 1-based starting lines.

    Note: The '# escape=' parser directive is not supported. Backslash ('\') is always
    treated as the line continuation character.
    """
    findings: list[DockerfileFinding] = []
    stages: set[str] = set()

    for line, start_line in _get_dockerfile_logical_lines(dockerfile_text):
        tokens = line.split()
        if not tokens or tokens[0].upper() != "FROM":
            continue

        remaining = tokens[1:]
        image_ref: str | None = None
        after_image: list[str] = []

        for idx, token in enumerate(remaining):
            if token.startswith("--"):
                continue
            image_ref = token
            after_image = remaining[idx + 1 :]
            break

        if not image_ref:
            continue

        stage_name: str | None = None
        for idx, token in enumerate(after_image):
            if token.upper() == "AS" and idx + 1 < len(after_image):
                stage_name = after_image[idx + 1]
                break

        is_scratch_or_prior_stage = image_ref.lower() == "scratch" or image_ref.lower() in stages

        if stage_name:
            stages.add(stage_name.lower())

        if is_scratch_or_prior_stage:
            continue

        _, _, digest = image_ref.rpartition("@")
        if bool(re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest)):
            classification = "pinned"
        elif "$" in image_ref:
            classification = "unresolved"
        else:
            classification = "unpinned"

        findings.append(
            DockerfileFinding(
                reference=image_ref,
                classification=classification,
                line_number=start_line,
            )
        )

    return findings


def check_docker_pinning(
    dockerfiles: list[dict[str, str | None]],
    discovery_complete: bool,
) -> CheckResult:
    """Check whether Dockerfile external base images are pinned to immutable digests."""
    unpinned_findings: list[tuple[str, str, int]] = []
    uncertain_locations: list[str] = []
    has_unresolved = False
    has_unavailable = False

    for df in dockerfiles:
        path = df.get("path", "")
        text = df.get("text")
        if text is None:
            has_unavailable = True
            uncertain_locations.append(path)
            continue

        findings = find_dockerfile_base_images_with_lines(text)
        for finding in findings:
            if finding.classification == "unpinned":
                unpinned_findings.append((finding.reference, path, finding.line_number))
            elif finding.classification == "unresolved":
                has_unresolved = True
                uncertain_locations.append(f"{path}:{finding.line_number}")

    # 1. Confirmed unpinned references produce fail
    if unpinned_findings:
        return CheckResult(
            check="docker_pinning",
            band="docker",
            status="fail",
            evidence=(
                f"Found {len(unpinned_findings)} Dockerfile base image reference(s) "
                "that are not pinned to a digest: " + ", ".join(ref for ref, _, _ in unpinned_findings)
            ),
            location="; ".join(f"{path}:{line}" for _, path, line in unpinned_findings),
        )

    # 2. Incomplete discovery produces review
    if not discovery_complete:
        return CheckResult(
            check="docker_pinning",
            band="docker",
            status="review",
            evidence="Dockerfile inventory could not be confirmed.",
            location="",
        )

    # 3. Complete empty discovery produces na
    if not dockerfiles:
        return CheckResult(
            check="docker_pinning",
            band="docker",
            status="na",
            evidence="Repository has no Dockerfiles.",
            location="",
        )

    # 4. Unresolved references or unavailable content produce review
    if has_unresolved or has_unavailable:
        return CheckResult(
            check="docker_pinning",
            band="docker",
            status="review",
            evidence=(
                "Dockerfile base images could not be fully verified due to "
                "unresolved references or unavailable content."
            ),
            location="; ".join(uncertain_locations),
        )

    # 5. Remaining cases produce pass
    return CheckResult(
        check="docker_pinning",
        band="docker",
        status="pass",
        evidence="All external base images are pinned by digest.",
        location="",
    )
