"""Tests for governance-config role mapping helpers."""

import pytest

from hiero_analytics.data_sources import governance_config
from hiero_analytics.data_sources.governance_config import (
    build_repo_role_lookup,
    fetch_governance_config,
    permission_to_role,
)


def test_fetch_governance_config_snapshots_valid_live_response(monkeypatch, tmp_path):
    """A validated live config is persisted for later offline previews."""
    snapshot = tmp_path / "governance.json"

    class Response:
        text = "teams: []\nrepositories: []\n"

        def raise_for_status(self):
            return None

    def get_response(_url, **_kwargs):
        return Response()

    monkeypatch.setattr(governance_config.requests, "get", get_response)

    result = fetch_governance_config(url="https://example.test/config.yaml", snapshot_path=snapshot)

    assert result == {"teams": [], "repositories": []}
    assert snapshot.exists()


def test_fetch_governance_config_uses_snapshot_offline(monkeypatch, tmp_path):
    """Offline governance loading never performs an HTTP request."""
    snapshot = tmp_path / "governance.json"
    snapshot.write_text('{"teams": [], "repositories": []}', encoding="utf-8")
    monkeypatch.setenv("HIERO_ANALYTICS_OFFLINE", "1")
    monkeypatch.setattr(
        governance_config.requests,
        "get",
        lambda *_args, **_kwargs: pytest.fail("HTTP request made in offline mode"),
    )

    assert fetch_governance_config(snapshot_path=snapshot) == {"teams": [], "repositories": []}


def test_fetch_governance_config_requires_snapshot_offline(monkeypatch, tmp_path):
    """A missing governance snapshot produces a clear offline error."""
    monkeypatch.setenv("HIERO_ANALYTICS_OFFLINE", "true")

    with pytest.raises(RuntimeError, match="requires a governance config snapshot"):
        fetch_governance_config(snapshot_path=tmp_path / "missing.json")


def test_fetch_governance_config_rejects_invalid_snapshot_offline(monkeypatch, tmp_path):
    """A snapshot that decodes but isn't a mapping still fails as a RuntimeError."""
    snapshot = tmp_path / "governance.json"
    snapshot.write_text("[]", encoding="utf-8")  # valid JSON, wrong shape
    monkeypatch.setenv("HIERO_ANALYTICS_OFFLINE", "1")

    with pytest.raises(RuntimeError, match="snapshot is invalid"):
        fetch_governance_config(snapshot_path=snapshot)


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
