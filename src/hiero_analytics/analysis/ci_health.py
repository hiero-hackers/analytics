"""Security checks for GitHub Actions workflow files."""

from __future__ import annotations

import re
from fnmatch import fnmatchcase

import yaml

from hiero_analytics.analysis.ci_health_types import CheckResult, CheckStatus

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


# Dependabot ecosystem -> root-level manifest file patterns. Data, not branching:
# supporting a new ecosystem means adding a row here. `github-actions` has no
# root manifest; it is detected from the workflow files instead.
ECOSYSTEM_MANIFESTS: dict[str, tuple[str, ...]] = {
    "npm": ("package.json",),
    "pip": ("requirements*.txt", "pyproject.toml", "setup.py", "Pipfile"),
    "docker": ("Dockerfile", "Dockerfile.*", "*.Dockerfile"),
    "gomod": ("go.mod",),
    "cargo": ("Cargo.toml",),
    "maven": ("pom.xml",),
    "gradle": ("build.gradle", "build.gradle.kts"),
    "composer": ("composer.json",),
    "bundler": ("Gemfile",),
    "swift": ("Package.swift",),
    "terraform": ("*.tf",),
    "pub": ("pubspec.yaml",),
}
GITHUB_ACTIONS_ECOSYSTEM = "github-actions"

# Dependabot ecosystems that cover the same manifests as one we map above.
ECOSYSTEM_ALIASES = {"uv": "pip"}

DEPENDABOT_CHECK = "dependabot_ecosystems"
DEPENDABOT_BAND = "dependabot"
DEPENDABOT_CONFIG_LOCATION = ".github/dependabot.yml"


def detect_manifests(
    root_entries: list[str],
    workflows: list[dict[str, str]],
) -> dict[str, list[str]]:
    """Return the manifest paths present in a repository, keyed by ecosystem."""
    detected: dict[str, list[str]] = {}

    for ecosystem, patterns in ECOSYSTEM_MANIFESTS.items():
        paths = sorted(name for name in root_entries if any(fnmatchcase(name, pattern) for pattern in patterns))
        if paths:
            detected[ecosystem] = paths

    if workflows:
        detected[GITHUB_ACTIONS_ECOSYSTEM] = sorted(f".github/workflows/{workflow['name']}" for workflow in workflows)

    return detected


def parse_dependabot_ecosystems(config_text: str) -> set[str] | None:
    """Return the ecosystems declared in a Dependabot config, or None if it is malformed."""
    try:
        config = yaml.safe_load(config_text)
    except yaml.YAMLError:
        return None

    if not isinstance(config, dict):
        return None

    updates = config.get("updates")

    if not isinstance(updates, list):
        return None

    declared: set[str] = set()

    for update in updates:
        if not isinstance(update, dict):
            return None

        ecosystem = update.get("package-ecosystem")

        if not isinstance(ecosystem, str) or not ecosystem:
            return None

        declared.add(ECOSYSTEM_ALIASES.get(ecosystem, ecosystem))

    return declared


def _dependabot_result(
    status: CheckStatus,
    evidence: str,
    location: str = "",
    subject: str = "",
) -> CheckResult:
    return CheckResult(
        check=DEPENDABOT_CHECK,
        band=DEPENDABOT_BAND,
        status=status,
        evidence=evidence,
        location=location,
        subject=subject,
    )


def check_dependabot_ecosystems(
    root_entries: list[str],
    workflows: list[dict[str, str]],
    dependabot_config: str | None,
) -> list[CheckResult]:
    """Cross-check the ecosystems Dependabot covers against the manifests a repo ships.

    Emits one row per ecosystem that is either present or declared. A missing or
    malformed config is its own finding. Ecosystems with no manifests report
    `na`, never `pass`.
    """
    manifests = detect_manifests(root_entries, workflows)

    if dependabot_config is None:
        if not manifests:
            return [_dependabot_result("na", "No supported ecosystem manifests and no Dependabot config.")]

        return [
            _dependabot_result(
                "fail",
                "No Dependabot config found, but manifests exist for: " + ", ".join(sorted(manifests)) + ".",
                DEPENDABOT_CONFIG_LOCATION,
                subject="config",
            )
        ]

    declared = parse_dependabot_ecosystems(dependabot_config)

    if declared is None:
        return [
            _dependabot_result(
                "fail",
                "Dependabot config could not be parsed or has no valid `updates` entries.",
                DEPENDABOT_CONFIG_LOCATION,
                subject="config",
            )
        ]

    results: list[CheckResult] = []

    for ecosystem in sorted(set(manifests) | declared):
        paths = manifests.get(ecosystem, [])
        location = "; ".join(paths)

        if paths and ecosystem in declared:
            results.append(
                _dependabot_result(
                    "pass", f"Declared in Dependabot; manifests: {', '.join(paths)}.", location, ecosystem
                )
            )
        elif paths:
            results.append(
                _dependabot_result(
                    "fail",
                    f"Not declared in Dependabot, but manifests exist: {', '.join(paths)}.",
                    location,
                    ecosystem,
                )
            )
        else:
            results.append(
                _dependabot_result(
                    "na",
                    "Declared in Dependabot, but no manifests found at the repository root.",
                    DEPENDABOT_CONFIG_LOCATION,
                    ecosystem,
                )
            )

    if not results:
        results.append(_dependabot_result("na", "Dependabot config declares no ecosystems and none are needed."))

    return results
