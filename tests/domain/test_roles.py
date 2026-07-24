"""Tests for GitHub-permission → governance-role normalization and role ranking."""

from __future__ import annotations

from hiero_analytics.domain.roles import ROLE_PRIORITY, permission_to_role


def test_permission_to_role_maps_github_permissions():
    """Each GitHub permission maps to its governance role; unknowns map to None."""
    assert permission_to_role("triage") == "triage"
    assert permission_to_role("write") == "committer"
    assert permission_to_role("maintain") == "maintainer"
    assert permission_to_role("admin") == "maintainer"
    assert permission_to_role("read") is None
    assert permission_to_role("PUSH") is None  # not a recognised permission string


def test_permission_to_role_is_case_insensitive():
    """Permission matching normalizes case before mapping."""
    assert permission_to_role("Admin") == "maintainer"
    assert permission_to_role("WRITE") == "committer"


def test_permission_to_role_rejects_non_strings():
    """A non-string permission (None, dict from a malformed payload) yields None."""
    assert permission_to_role(None) is None
    assert permission_to_role({"unexpected": "shape"}) is None


def test_role_priority_orders_maintainer_above_committer_above_triage():
    """ROLE_PRIORITY ranks governance roles so the highest wins on conflict."""
    assert ROLE_PRIORITY["maintainer"] > ROLE_PRIORITY["committer"] > ROLE_PRIORITY["triage"]
    assert ROLE_PRIORITY["triage"] > ROLE_PRIORITY["general_user"]
