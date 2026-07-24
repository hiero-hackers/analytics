"""Tests for repository-name helpers."""

from __future__ import annotations

from hiero_analytics.domain.repos import bare_repo


def test_bare_repo_strips_the_owner_prefix():
    """``owner/name`` collapses to just the repository name."""
    assert bare_repo("hiero-ledger/hiero-sdk-python") == "hiero-sdk-python"


def test_bare_repo_leaves_an_unqualified_name_untouched():
    """A name with no owner prefix is returned unchanged."""
    assert bare_repo("solo") == "solo"
