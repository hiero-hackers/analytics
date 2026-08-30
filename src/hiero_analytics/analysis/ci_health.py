"""Security checks for GitHub Actions workflow files."""

from __future__ import annotations

import re

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


def check_workflows(
    workflows: list[dict[str, str]],
) -> dict[str, list[str]]:
    """Check workflow files for GitHub Actions that are not SHA pinned."""
    return {workflow["name"]: find_unpinned_actions(workflow["text"]) for workflow in workflows}
