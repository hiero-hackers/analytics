"""Tests for GitHub Actions workflow security checks."""

from hiero_analytics.analysis.workflow_security import (
    check_workflows,
    extract_action_references,
    find_unpinned_actions,
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


def test_check_workflows() -> None:
    """Test security checks across multiple workflow files."""
    workflows = [
        {
            "name": "build.yml",
            "text": """
            jobs:
              build:
                steps:
                  - uses: actions/checkout@v4
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

    assert check_workflows(workflows) == {
        "build.yml": ["actions/checkout@v4"],
        "release.yml": [],
    }
