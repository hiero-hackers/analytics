"""Tests for the org registry — the single source of truth for org capabilities.

The point of ``config.orgs`` is that onboarding an org is adding one line, and
everything org-shaped follows. These tests pin the capabilities the rest of the
system reads, so the composition can change without silently breaking the
"register it once" contract.
"""

from __future__ import annotations

import logging

from hiero_analytics.config import orgs
from hiero_analytics.config.orgs import (
    DEFAULT_PRIMARY_ORG,
    ORGS,
    extra_orgs,
    governance_urls,
    has_org_overview,
    is_governed,
    is_primary,
    org_names,
    profile_for,
    repo_category_overrides,
)

PRIMARY = "hiero-ledger"
COMPOSITION = "hiero-hackers"


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


def test_governance_urls_cover_exactly_the_governed_orgs(monkeypatch):
    """The derived map has one entry per governed org, keyed by its name."""
    monkeypatch.delenv("GOVERNANCE_CONFIG_URL", raising=False)

    urls = governance_urls()

    assert set(urls) == {entry.name for entry in ORGS if entry.governed}
    assert urls[PRIMARY] == profile_for(PRIMARY).governance_url


def test_governance_config_url_overrides_only_the_primary_source(monkeypatch):
    """The env override repoints the primary org, leaving other governed orgs alone."""
    monkeypatch.setenv("GOVERNANCE_CONFIG_URL", "https://example.com/override.yaml")

    urls = governance_urls()

    assert urls[orgs._primary_org()] == "https://example.com/override.yaml"
    # Every other governed org keeps its own profile URL.
    for entry in ORGS:
        if entry.governed and entry.name != orgs._primary_org():
            assert urls[entry.name] == entry.governance_url


# capability predicates


def test_is_governed_follows_the_registry():
    """is_governed reads the registry, so an unregistered org is never governed."""
    assert is_governed(PRIMARY)
    assert not is_governed(COMPOSITION)
    assert not is_governed("some-org-not-registered")


def test_has_org_overview_follows_the_registry():
    """has_org_overview reads the registry; an unregistered org has no overview."""
    assert has_org_overview(COMPOSITION)
    assert not has_org_overview(PRIMARY)
    assert not has_org_overview("some-org-not-registered")


def test_is_primary_follows_the_environment(monkeypatch):
    """Pointing the run at another org moves the primary-org content with it."""
    monkeypatch.setenv("GITHUB_ORG", COMPOSITION)

    assert is_primary(COMPOSITION)
    assert not is_primary(PRIMARY)


def test_org_names_lists_every_registered_org():
    """Every org name is exported, registry order — primary first."""
    assert org_names()[0] == DEFAULT_PRIMARY_ORG
    assert set(org_names()) == {entry.name for entry in ORGS}


# the extra-orgs view


def test_extra_orgs_defaults_to_the_registry(monkeypatch):
    """With no env filter, the registry's ``extra`` orgs are rendered."""
    monkeypatch.delenv("GITHUB_EXTRA_ORGS", raising=False)

    assert extra_orgs() == [entry.name for entry in ORGS if entry.extra]


def test_extra_orgs_empty_env_disables_every_extra(monkeypatch):
    """An empty allow-list renders no extra orgs, without editing the registry."""
    monkeypatch.setenv("GITHUB_EXTRA_ORGS", "")

    assert extra_orgs() == []


def test_extra_orgs_env_filters_to_known_orgs(monkeypatch):
    """The env allow-list narrows the registry's extra orgs and ignores strays."""
    monkeypatch.setenv("GITHUB_EXTRA_ORGS", "hiero-hackers,unregistered-org")

    assert extra_orgs() == ["hiero-hackers"]


def test_extra_orgs_warns_about_dropped_orgs(monkeypatch, caplog):
    """Requesting an org outside the registry logs what gets ignored.

    So ``GITHUB_EXTRA_ORGS`` never quietly does nothing: an unregistered name is
    dropped (only registry ``extra`` orgs render), and the warning names it.
    """
    monkeypatch.setenv("GITHUB_EXTRA_ORGS", "hiero-hackers,some-new-org")

    with caplog.at_level(logging.WARNING, logger=orgs.logger.name):
        assert extra_orgs() == ["hiero-hackers"]

    assert any("some-new-org" in record.getMessage() for record in caplog.records)


# repo category overrides


def test_repo_category_overrides_merges_every_orgs_entries():
    """The overrides map unions each org's explicit repo->category entries."""
    overrides = repo_category_overrides()

    expected = {repo: category for entry in ORGS for repo, category in entry.repo_categories.items()}
    assert overrides == expected
    assert "hiero-sdk-csharp" in overrides
