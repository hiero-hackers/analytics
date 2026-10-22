"""Tests for the org registry — the single source of truth for org capabilities.

The point of ``config.orgs`` is that onboarding an org is adding one profile, and
everything org-shaped follows. These tests pin the capabilities and the
environment views the rest of the system reads, so the composition can change
without silently breaking the "register it once" contract.
"""

from __future__ import annotations

import logging

import pytest

from hiero_analytics.config import orgs
from hiero_analytics.config.orgs import (
    CAPABILITIES,
    DEFAULT_PRIMARY_ORG,
    DISCORD,
    GOVERNED,
    HIPS,
    ORG_OVERVIEW,
    ORGS,
    OrgProfile,
    blanket_teams,
    capabilities_of,
    discord_org,
    extra_orgs,
    governance_urls,
    has_org_overview,
    hip_proposals_repo,
    is_governed,
    org_names,
    primary_org,
    profile_for,
    profile_or_default,
    rendered_orgs,
    repo_category_overrides,
    trial_orgs,
)

PRIMARY = "hiero-ledger"
COMPOSITION = "hiero-hackers"


@pytest.fixture
def registry(monkeypatch):
    """Swap in a small synthetic registry; returns a setter for the env views."""
    profiles = (
        OrgProfile(name="primary-org", governed=True, governance_url="https://example.test/p.yaml"),
        OrgProfile(name="governed-org", governed=True, governance_url="https://example.test/g.yaml", extra=True),
        OrgProfile(name="plain-org", org_overview=True, extra=True),
        OrgProfile(name="dormant-org"),  # registered, but not rendered by the full run
    )
    monkeypatch.setattr(orgs, "ORGS", profiles)
    monkeypatch.setenv("GITHUB_ORG", "primary-org")
    return profiles


# registry shape


def test_primary_org_is_governed_with_a_config_url():
    """The primary org publishes a governance config and has a source for it."""
    profile = profile_for(PRIMARY)

    assert profile is not None
    assert profile.governed
    assert profile.governance_url


def test_composition_org_is_ungoverned_with_an_overview():
    """The composition org is ungoverned but gets the org-overview cards."""
    profile = profile_for(COMPOSITION)

    assert profile is not None
    assert not profile.governed
    assert profile.governance_url is None
    assert profile.org_overview
    assert profile.extra


def test_governed_orgs_have_a_config_url_and_ungoverned_ones_do_not():
    """``governed`` and a governance source always agree across the registry."""
    for entry in ORGS:
        assert entry.governed == (entry.governance_url is not None), entry.name


def test_registry_logins_are_unique_case_insensitively():
    """GitHub logins are case-insensitive, so two spellings would be one org twice."""
    lowered = [entry.name.lower() for entry in ORGS]
    assert len(lowered) == len(set(lowered))


def test_registry_brand_keys_are_url_safe():
    """A brand key becomes a path under web/public/brand/, so it must be a plain slug."""
    for entry in ORGS:
        if entry.brand is not None:
            assert entry.brand.replace("-", "").isalnum() and entry.brand == entry.brand.lower(), entry.name


def test_governance_urls_cover_exactly_the_governed_orgs(monkeypatch):
    """The derived map has one entry per governed org, keyed by its name."""
    monkeypatch.delenv("GOVERNANCE_CONFIG_URL", raising=False)

    urls = governance_urls()

    assert set(urls) == {entry.name for entry in ORGS if entry.governed}
    assert urls[PRIMARY] == profile_for(PRIMARY).governance_url


def test_governance_config_url_overrides_only_the_primary_source(monkeypatch, registry):
    """The env override repoints the primary org, leaving other governed orgs alone."""
    monkeypatch.setenv("GOVERNANCE_CONFIG_URL", "https://example.com/override.yaml")

    urls = governance_urls()

    assert urls["primary-org"] == "https://example.com/override.yaml"
    assert urls["governed-org"] == "https://example.test/g.yaml"


# capabilities


def test_capabilities_follow_the_profile_fields():
    """Each capability is derived from exactly one profile field."""
    full = OrgProfile(
        name="x",
        governed=True,
        governance_url="https://example.test/x.yaml",
        org_overview=True,
        hip_proposals_repo="x/proposals",
        discord=True,
    )

    assert full.capabilities == CAPABILITIES == {GOVERNED, ORG_OVERVIEW, HIPS, DISCORD}
    assert OrgProfile(name="y").capabilities == frozenset()


def test_the_primary_org_owns_hips_and_discord():
    """HIPs and the Discord export belong to hiero-ledger by profile, not by being primary."""
    assert capabilities_of(PRIMARY) >= {GOVERNED, HIPS, DISCORD}
    assert capabilities_of(COMPOSITION) == {ORG_OVERVIEW}
    assert discord_org() == PRIMARY


def test_unregistered_orgs_get_an_empty_default_profile():
    """An unregistered org (a trial run) is plain: no capabilities, no teams, its login as label."""
    profile = profile_or_default("some-org-not-registered")

    assert profile.name == profile.label == "some-org-not-registered"
    assert capabilities_of("some-org-not-registered") == frozenset()
    assert blanket_teams("some-org-not-registered") == frozenset()
    assert hip_proposals_repo("some-org-not-registered") is None


def test_predicates_follow_the_registry():
    """The capability predicates read the registry; an unregistered org has none."""
    assert is_governed(PRIMARY)
    assert not is_governed(COMPOSITION)
    assert not is_governed("some-org-not-registered")
    assert has_org_overview(COMPOSITION)
    assert not has_org_overview(PRIMARY)


def test_blanket_teams_are_per_org():
    """The primary org's org-wide teams live on its profile."""
    assert "tsc" in blanket_teams(PRIMARY)
    assert blanket_teams(COMPOSITION) == frozenset()


def test_hip_proposals_repo_env_overrides_the_profile(monkeypatch):
    """HIP_PROPOSALS_REPO repoints an org that has the capability, and only such an org."""
    monkeypatch.setenv("HIP_PROPOSALS_REPO", "fork/proposals")

    assert hip_proposals_repo(PRIMARY) == "fork/proposals"
    assert hip_proposals_repo(COMPOSITION) is None


def test_label_falls_back_to_the_login():
    """The dashboard label is the display name when set, the login otherwise."""
    assert OrgProfile(name="lfdt-x", display_name="LFDT X").label == "LFDT X"
    assert OrgProfile(name="lfdt-x").label == "lfdt-x"


# the primary org and the rendered set


def test_primary_org_follows_the_environment(monkeypatch):
    """GITHUB_ORG picks the primary org; unset or empty falls back to the default."""
    monkeypatch.setenv("GITHUB_ORG", COMPOSITION)
    assert primary_org() == COMPOSITION

    monkeypatch.setenv("GITHUB_ORG", "")
    assert primary_org() == DEFAULT_PRIMARY_ORG

    monkeypatch.delenv("GITHUB_ORG")
    assert primary_org() == DEFAULT_PRIMARY_ORG


def test_org_names_lists_every_registered_org():
    """Every org name is exported, in registry order."""
    assert org_names()[0] == DEFAULT_PRIMARY_ORG
    assert set(org_names()) == {entry.name for entry in ORGS}


def test_extra_orgs_defaults_to_the_registry(registry):
    """With no env filter, the registry's ``extra`` orgs are rendered."""
    assert extra_orgs() == ["governed-org", "plain-org"]


def test_extra_orgs_never_repeat_the_primary(monkeypatch, registry):
    """An extra org made primary for a run is not rendered twice."""
    monkeypatch.setenv("GITHUB_ORG", "plain-org")

    assert extra_orgs() == ["governed-org"]
    assert rendered_orgs() == ["plain-org", "governed-org"]


def test_extra_orgs_empty_env_disables_every_extra(monkeypatch, registry):
    """An empty allow-list renders no extra orgs, without editing the registry."""
    monkeypatch.setenv("GITHUB_EXTRA_ORGS", "")

    assert extra_orgs() == []


def test_extra_orgs_env_filters_and_warns_about_unregistered(monkeypatch, caplog, registry):
    """The allow-list narrows the extras; a name it cannot honour is named in a warning."""
    monkeypatch.setenv("GITHUB_EXTRA_ORGS", "plain-org,some-new-org,dormant-org")

    with caplog.at_level(logging.WARNING, logger=orgs.logger.name):
        assert extra_orgs() == ["plain-org"]

    message = " ".join(record.getMessage() for record in caplog.records)
    assert "some-new-org" in message and "dormant-org" in message
    assert "HIERO_ANALYTICS_TRIAL_ORGS" in message


def test_trial_orgs_are_added_after_the_registry(monkeypatch, caplog, registry):
    """Trial orgs join the run after the primary and extra orgs, once each."""
    monkeypatch.setenv("HIERO_ANALYTICS_TRIAL_ORGS", " candidate-org , plain-org ,")

    with caplog.at_level(logging.INFO, logger=orgs.logger.name):
        assert trial_orgs() == ["candidate-org", "plain-org"]
        assert rendered_orgs() == ["primary-org", "governed-org", "plain-org", "candidate-org"]

    assert any("candidate-org" in record.getMessage() for record in caplog.records)


def test_rendered_orgs_is_just_the_primary_without_extras(monkeypatch, registry):
    """A run with extras disabled and no trials renders the primary org alone."""
    monkeypatch.setenv("GITHUB_EXTRA_ORGS", "")

    assert rendered_orgs() == ["primary-org"]


# repo category overrides


def test_repo_category_overrides_merges_every_orgs_entries():
    """The overrides map unions each org's explicit repo->category entries."""
    overrides = repo_category_overrides()

    expected = {repo: category for entry in ORGS for repo, category in entry.repo_categories.items()}
    assert overrides == expected
    assert "hiero-sdk-csharp" in overrides
