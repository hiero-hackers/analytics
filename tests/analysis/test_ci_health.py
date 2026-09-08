"""Tests for GitHub Actions workflow security checks."""

from hiero_analytics.analysis.ci_health import (
    check_actions_sha_pinned,
    check_explicit_permissions,
    extract_action_references,
    find_permissions_with_lines,
    find_unpinned_actions,
    find_unpinned_actions_with_lines,
    is_sha_pinned,
)


def test_extract_action_references() -> None:
    """Test extraction of Actions references from workflow YAML."""
    workflow = """
    jobs:
      build:
        steps:
          - uses: actions/checkout@v4
          - uses: actions/setup-java@main
        permissions:
          uses: something/example@v1
    """

    assert extract_action_references(workflow) == [
        "actions/checkout@v4",
        "actions/setup-java@main",
        "something/example@v1",
    ]


def test_is_sha_pinned() -> None:
    """Test detection of full commit SHA references."""
    assert is_sha_pinned("actions/checkout@0123456789abcdef0123456789abcdef01234567")
    assert not is_sha_pinned("actions/checkout@v4")
    assert not is_sha_pinned("actions/checkout@main")


def test_is_sha_pinned_rejects_invalid_sha_lengths() -> None:
    """Test that only full-length commit SHAs are accepted."""
    assert not is_sha_pinned("actions/checkout@0123456789abcdef")
    assert not is_sha_pinned("actions/checkout@0123456789abcdef0123456789abcdef012345678")


def test_find_unpinned_actions() -> None:
    """Test detection of Actions references that are not SHA pinned."""
    workflow = """
    jobs:
      build:
        steps:
          - uses: actions/checkout@v4
          - uses: actions/setup-java@0123456789abcdef0123456789abcdef01234567
          - uses: actions/setup-node@main
    """

    assert find_unpinned_actions(workflow) == [
        "actions/checkout@v4",
        "actions/setup-node@main",
    ]


def test_find_unpinned_actions_with_lines() -> None:
    """Test detection of unpinned Actions references with line numbers."""
    workflow = """name: CI

jobs:
  build:
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@0123456789abcdef0123456789abcdef01234567
      - uses: actions/setup-node@main
"""

    assert find_unpinned_actions_with_lines(workflow) == [
        ("actions/checkout@v4", 6),
        ("actions/setup-node@main", 8),
    ]


def test_check_actions_sha_pinned_fails_for_unpinned_actions() -> None:
    """Test that unpinned Actions produce a failing check result."""
    workflows = [
        {
            "name": "build.yml",
            "text": """jobs:
  build:
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@0123456789abcdef0123456789abcdef01234567
""",
        },
        {
            "name": "release.yml",
            "text": """jobs:
  release:
    steps:
      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567
""",
        },
    ]

    result = check_actions_sha_pinned(workflows)

    assert result.check == "actions_sha_pinned"
    assert result.band == "actions"
    assert result.status == "fail"
    assert "actions/checkout@v4" in result.evidence
    assert result.location == ".github/workflows/build.yml:4"


def test_check_actions_sha_pinned_passes_when_all_actions_are_pinned() -> None:
    """Test that fully pinned workflows produce a passing check result."""
    workflows = [
        {
            "name": "build.yml",
            "text": """
            jobs:
              build:
                steps:
                  - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567
                  - uses: actions/setup-java@0123456789abcdef0123456789abcdef01234567
            """,
        },
        {
            "name": "release.yml",
            "text": """
            jobs:
              release:
                steps:
                  - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567
            """,
        },
    ]

    result = check_actions_sha_pinned(workflows)

    assert result.check == "actions_sha_pinned"
    assert result.band == "actions"
    assert result.status == "pass"
    assert result.evidence == "All GitHub Actions are pinned to full commit SHAs."
    assert result.location == ""


def test_find_permissions_with_lines() -> None:
    """Test detection of explicit permissions declarations with line numbers."""
    workflow = """name: CI

permissions:
  contents: read

jobs:
  build:
    permissions:
      packages: read
"""

    assert find_permissions_with_lines(workflow) == [3, 8]


def test_check_explicit_permissions_passes_with_top_level_permissions() -> None:
    """Test that top-level permissions produce a passing check result."""
    workflows = [
        {
            "name": "build.yml",
            "text": """name: CI

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
""",
        }
    ]

    result = check_explicit_permissions(workflows)

    assert result.check == "explicit_permissions"
    assert result.band == "permissions"
    assert result.status == "pass"
    assert "All 1 workflow(s)" in result.evidence
    assert result.location == ".github/workflows/build.yml:3"


def test_check_explicit_permissions_passes_with_job_permissions() -> None:
    """Test that job-level permissions produce a passing check result."""
    workflows = [
        {
            "name": "build.yml",
            "text": """name: CI

jobs:
  build:
    permissions:
      contents: read
    runs-on: ubuntu-latest
""",
        }
    ]

    result = check_explicit_permissions(workflows)

    assert result.check == "explicit_permissions"
    assert result.band == "permissions"
    assert result.status == "pass"
    assert result.location == ".github/workflows/build.yml:5"


def test_check_explicit_permissions_passes_with_empty_permissions() -> None:
    """Test that an explicit empty permissions block passes."""
    workflows = [
        {
            "name": "build.yml",
            "text": """name: CI

permissions: {}

jobs:
  build:
    runs-on: ubuntu-latest
""",
        }
    ]

    result = check_explicit_permissions(workflows)

    assert result.check == "explicit_permissions"
    assert result.band == "permissions"
    assert result.status == "pass"
    assert result.location == ".github/workflows/build.yml:3"


def test_check_explicit_permissions_fails_when_permissions_are_missing() -> None:
    """Test that missing permissions produce a failing check result."""
    workflows = [
        {
            "name": "build.yml",
            "text": """name: CI

jobs:
  build:
    runs-on: ubuntu-latest
""",
        },
        {
            "name": "release.yml",
            "text": """name: Release

jobs:
  release:
    runs-on: ubuntu-latest
""",
        },
    ]

    result = check_explicit_permissions(workflows)

    assert result.check == "explicit_permissions"
    assert result.band == "permissions"
    assert result.status == "fail"
    assert "2 workflow(s)" in result.evidence
    assert "build.yml" in result.evidence
    assert "release.yml" in result.evidence
    assert result.location == (".github/workflows/build.yml; .github/workflows/release.yml")


def test_check_explicit_permissions_passes_when_all_workflows_declare_permissions() -> None:
    """Test that all workflows with explicit permissions pass."""
    workflows = [
        {
            "name": "build.yml",
            "text": """name: CI

permissions:
  contents: read
""",
        },
        {
            "name": "release.yml",
            "text": """name: Release

jobs:
  release:
    permissions:
      contents: read
""",
        },
    ]

    result = check_explicit_permissions(workflows)

    assert result.check == "explicit_permissions"
    assert result.band == "permissions"
    assert result.status == "pass"
    assert result.evidence == ("All 2 workflow(s) explicitly declare GitHub Actions permissions.")
    assert result.location == (".github/workflows/build.yml:3; .github/workflows/release.yml:5")


def test_check_explicit_permissions_returns_na_without_workflows() -> None:
    """Test that repositories without workflows return not applicable."""
    result = check_explicit_permissions([])

    assert result.check == "explicit_permissions"
    assert result.band == "permissions"
    assert result.status == "na"
    assert result.evidence == "Repository has no GitHub Actions workflows."
    assert result.location == ""
