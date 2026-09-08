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
