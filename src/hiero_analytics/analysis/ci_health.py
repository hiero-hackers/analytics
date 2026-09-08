"""Security checks for GitHub Actions workflow files."""

from __future__ import annotations

import re

from hiero_analytics.analysis.ci_health_types import CheckResult

USES_PATTERN = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.MULTILINE)


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


def find_unpinned_actions_with_lines(workflow_text: str) -> list[tuple[str, int]]:
    """Return unpinned GitHub Actions references with their line numbers."""
    findings: list[tuple[str, int]] = []

    for line_number, line in enumerate(workflow_text.splitlines(), start=1):
        match = USES_PATTERN.match(line)
        if match:
            reference = match.group(1)
            if not is_sha_pinned(reference):
                findings.append((reference, line_number))

    return findings


def check_actions_sha_pinned(
    workflows: list[dict[str, str]],
) -> CheckResult:
    """Check whether GitHub Actions references are pinned to commit SHAs."""
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
