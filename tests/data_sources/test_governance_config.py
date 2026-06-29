"""Tests for governance-config role mapping helpers."""

from hiero_analytics.data_sources.governance_config import (
    build_repo_role_lookup,
    count_distinct_role_holders_by_role,
    permission_to_role,
)


def test_permission_to_role_maps_repo_permissions():
    """Repository permissions should normalize into maintainer-pipeline roles."""
    assert permission_to_role("triage") == "triage"
    assert permission_to_role("write") == "committer"
    assert permission_to_role("maintain") == "maintainer"
    assert permission_to_role("admin") == "maintainer"
    assert permission_to_role("read") is None


def test_build_repo_role_lookup_assigns_highest_role_per_user():
    """Repo-affined teams should resolve each user to their highest repo role."""
    config = {
        "teams": [
            {
                "name": "repo-a-triage",
                "maintainers": ["triage-lead"],
                "members": ["alice"],
            },
            {
                "name": "repo-a-committers",
                "maintainers": ["commit-lead"],
                "members": ["alice", "bob"],
            },
            {
                "name": "repo-a-maintainers",
                "maintainers": ["maint-lead"],
                "members": ["carol"],
            },
        ],
        "repositories": [
            {
                "name": "repo-a",
                "teams": {
                    "repo-a-triage": "triage",
                    "repo-a-committers": "write",
                    "repo-a-maintainers": "maintain",
                },
            }
        ],
    }

    repo_role_lookup = build_repo_role_lookup(config)

    assert repo_role_lookup["repo-a"]["triage-lead"] == "triage"
    assert repo_role_lookup["repo-a"]["alice"] == "committer"
    assert repo_role_lookup["repo-a"]["bob"] == "committer"
    assert repo_role_lookup["repo-a"]["maint-lead"] == "maintainer"
    assert repo_role_lookup["repo-a"]["carol"] == "maintainer"


def test_build_repo_role_lookup_excludes_blanket_but_keeps_explicit_grants():
    """Blanket org-wide teams are excluded, but every explicitly-granted team counts.

    A team granted to several repos (here solo-docs-admins on both solo and solo-docs)
    must count on all of them — that cross-repo grant used to be dropped.
    """
    config = {
        "teams": [
            {"name": "solo-admins", "maintainers": ["solo-admin"], "members": []},
            {"name": "solo-docs-admins", "maintainers": ["docs-admin"], "members": []},
            {"name": "github-maintainers", "maintainers": ["global-admin"], "members": []},
        ],
        "repositories": [
            {
                "name": "solo",
                "teams": {
                    "solo-admins": "admin",
                    "solo-docs-admins": "admin",  # also granted here, not just on solo-docs
                    "github-maintainers": "maintain",  # blanket -> excluded
                },
            },
            {"name": "solo-docs", "teams": {"solo-docs-admins": "admin", "github-maintainers": "maintain"}},
        ],
    }

    repo_role_lookup = build_repo_role_lookup(config)

    # blanket github-maintainers excluded (both repos have a domain maintainer);
    # solo-docs-admins counts on solo too.
    assert repo_role_lookup["solo"] == {"solo-admin": "maintainer", "docs-admin": "maintainer"}
    assert repo_role_lookup["solo-docs"] == {"docs-admin": "maintainer"}


def test_build_repo_role_lookup_blanket_fallback_for_meta_repos():
    """A repo with no domain maintainer team is credited via blanket maintain teams."""
    config = {
        "teams": [
            {"name": "github-maintainers", "maintainers": ["org-admin"], "members": []},
            {"name": "tsc", "maintainers": ["tsc-chair"], "members": []},
            {"name": "governance-write", "maintainers": [], "members": ["writer1", "writer2"]},
        ],
        "repositories": [
            {
                "name": "governance",
                "teams": {
                    "github-maintainers": "maintain",  # blanket maintain
                    "tsc": "maintain",  # blanket maintain
                    "governance-write": "write",  # domain committer team
                },
            },
        ],
    }

    lookup = build_repo_role_lookup(config)
    # governance-write -> committers; no domain maintainer, so blanket maintain teams fill in.
    assert lookup["governance"]["writer1"] == "committer"
    assert lookup["governance"]["org-admin"] == "maintainer"
    assert lookup["governance"]["tsc-chair"] == "maintainer"


def test_build_repo_role_lookup_normalizes_usernames():
    """GitHub usernames should be trimmed and matched case-insensitively."""
    config = {
        "teams": [
            {
                "name": "hiero-website-committers",
                "maintainers": ["LeadMaintainer "],
                "members": ["ExplorerIII"],
            }
        ],
        "repositories": [
            {
                "name": "hiero-website",
                "teams": {
                    "hiero-website-committers": "write",
                },
            }
        ],
    }

    repo_role_lookup = build_repo_role_lookup(config)

    assert repo_role_lookup["hiero-website"]["leadmaintainer"] == "committer"
    assert repo_role_lookup["hiero-website"]["exploreriii"] == "committer"


def test_count_distinct_role_holders_by_role_counts_each_user_once_per_role():
    """Distinct role-holder counts should deduplicate users within each role."""
    repo_role_lookup = {
        "repo-a": {
            "alice": "maintainer",
            "bob": "committer",
        },
        "repo-b": {
            "alice": "committer",
            "carol": "committer",
        },
    }

    counts = count_distinct_role_holders_by_role(repo_role_lookup)

    assert counts["maintainer"] == 1
    assert counts["committer"] == 3
