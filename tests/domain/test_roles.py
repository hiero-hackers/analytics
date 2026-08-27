"""Tests for GitHub-permission → governance-role normalization and role ranking."""

from __future__ import annotations

from hiero_analytics.domain.roles import (
    ROLE_PRIORITY,
    highest_role_holders,
    highest_role_lookup,
    permission_to_role,
)


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


def test_highest_role_holders_partitions_people_by_seniority():
    """Each person lands in exactly one role bucket: the most senior seat they hold anywhere."""
    role_lookup = {
        "org/a": {"alice": "maintainer", "bob": "committer", "dave": "triage"},
        "org/b": {"alice": "committer", "bob": "committer", "carol": "triage", "dave": "committer"},
        "org/c": {"dave": "maintainer", "erin": "general_user"},
    }

    maintainers = highest_role_holders(role_lookup, "maintainer")
    committers = highest_role_holders(role_lookup, "committer")
    triagers = highest_role_holders(role_lookup, "triage")

    assert maintainers == {"alice", "dave"}  # dave holds all three; maintainer wins
    assert committers == {"bob"}
    assert triagers == {"carol"}
    assert not (maintainers & committers) and not (committers & triagers) and not (maintainers & triagers)
    # Everyone with a governance seat is counted exactly once across the buckets.
    assert len(maintainers | committers | triagers) == 4  # alice, dave, bob, carol (erin is general_user)


def test_highest_role_holders_matches_a_plain_union_for_maintainer():
    """Maintainer tops ROLE_PRIORITY, so the resolver cannot drop anyone the old union kept."""
    role_lookup = {
        "org/a": {"alice": "maintainer", "bob": "committer"},
        "org/b": {"bob": "maintainer", "carol": "triage"},
    }
    union = {login for holders in role_lookup.values() for login, role in holders.items() if role == "maintainer"}

    assert highest_role_holders(role_lookup, "maintainer") == union


def test_highest_role_holders_empty_lookup():
    """An empty governance config resolves to an empty set, not an error."""
    assert highest_role_holders({}, "maintainer") == set()


def test_highest_role_lookup_drops_seats_held_by_someone_more_senior_elsewhere():
    """A person who maintains anywhere never counts as a repo's committer."""
    role_lookup = {
        "org/a": {"alice": "maintainer", "bob": "committer"},
        "org/b": {"alice": "committer", "bob": "committer"},
    }

    committers = highest_role_lookup(role_lookup, "committer")

    assert committers == {"org/a": {"bob": "committer"}, "org/b": {"bob": "committer"}}


def test_highest_role_lookup_leaves_maintainer_seats_intact():
    """Maintainer tops the priority order, so its per-repo seats are never filtered out."""
    role_lookup = {"org/a": {"alice": "maintainer", "bob": "committer"}}

    assert highest_role_lookup(role_lookup, "maintainer") == {"org/a": {"alice": "maintainer"}}
