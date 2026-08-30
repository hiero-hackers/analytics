"""Tests for GitHub Actions workflow security checks."""

from hiero_analytics.analysis.workflow_security import (
    extract_action_references,
    find_unpinned_actions,
    is_sha_pinned,
)


def test_extract_action_references() -> None:
    """Test extraction of GitHub Actions references from workflow YAML."""
    workflow = """
    jobs:
      build:
        steps:
          - uses: actions/checkout@v4
          - uses: actions/setup-java@main
    """

    assert extract_action_references(workflow) == [
        "actions/checkout@v4",
        "actions/setup-java@main",
    ]


def test_is_sha_pinned() -> None:
    """Test detection of full commit SHA references."""
    assert is_sha_pinned("actions/checkout@0123456789abcdef0123456789abcdef01234567")
    assert not is_sha_pinned("actions/checkout@v4")
    assert not is_sha_pinned("actions/checkout@main")


def test_find_unpinned_actions() -> None:
    """Test detection of Actions references that are not SHA pinned."""
    workflow = """
    jobs:
      build:
        steps:
          - uses: actions/checkout@v4
          - uses: actions/setup-java@0123456789abcdef0123456789abcdef01234567
    """

    assert find_unpinned_actions(workflow) == [
        "actions/checkout@v4",
    ]
