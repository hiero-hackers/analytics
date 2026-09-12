"""Security checks for GitHub Actions workflow files."""

from __future__ import annotations

import re

from hiero_analytics.analysis.ci_health_types import CheckResult

USES_PATTERN = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.MULTILINE)
PERMISSIONS_PATTERN = re.compile(r"^\s*permissions\s*:", re.MULTILINE)


def extract_action_references(workflow_text: str) -> list[str]:
    """Extract GitHub Actions `uses:` references from workflow YAML."""
    return USES_PATTERN.findall(workflow_text)


def is_sha_pinned(reference: str) -> bool:
    """Return whether an Actions reference is pinned to a full commit SHA."""
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
    """Check whether each GitHub Actions workflow explicitly declares permissions."""
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
        permission_lines = find_permissions_with_lines(workflow["text"])

        if not permission_lines:
            missing_permissions.append(workflow["name"])
            locations.append(f".github/workflows/{workflow['name']}")
            continue

        locations.extend(f".github/workflows/{workflow['name']}:{line_number}" for line_number in permission_lines)

    if not missing_permissions:
        return CheckResult(
            check="explicit_permissions",
            band="permissions",
            status="pass",
            evidence=(f"All {len(workflows)} workflow(s) explicitly declare GitHub Actions permissions."),
            location="; ".join(locations),
        )

    return CheckResult(
        check="explicit_permissions",
        band="permissions",
        status="fail",
        evidence=(
            f"Found {len(missing_permissions)} workflow(s) without an "
            "explicit permissions declaration: " + ", ".join(missing_permissions)
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


def find_workflow_names_containing(
    workflows: list[dict[str, str]],
    patterns: tuple[str, ...],
) -> list[str]:
    """Return workflow names whose names or contents match known patterns."""
    matches: list[str] = []

    for workflow in workflows:
        name = workflow["name"]
        text = workflow["text"].lower()

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
