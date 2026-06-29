"""Tests for semantic repository categorization."""

from __future__ import annotations

from hiero_analytics.analysis.repo_categories import CATEGORY_ORDER, REPO_CATEGORIES, categorize_repo


def test_curated_map_and_owner_prefix_stripped():
    """Curated repos resolve; an ``owner/name`` prefix is ignored."""
    assert categorize_repo("hiero-sdk-python") == "SDKs"
    assert categorize_repo("hiero-ledger/hiero-consensus-node") == "Core network"
    assert categorize_repo("governance") == "Governance"
    assert categorize_repo("hiero-website") == "Docs / Web"


def test_keyword_fallback_for_unknown_repos():
    """Unknown repos fall back to keyword rules; DID beats the generic SDK rule."""
    assert categorize_repo("hiero-sdk-kotlin") == "SDKs"  # not curated, keyword 'sdk'
    assert categorize_repo("hiero-did-sdk-go") == "Identity / DID"  # 'did' before 'sdk'
    assert categorize_repo("something-unmapped") == "Other"


def test_every_curated_category_is_in_the_order_list():
    """All curated categories appear in CATEGORY_ORDER (so the legend can place them)."""
    assert set(REPO_CATEGORIES.values()) <= set(CATEGORY_ORDER)
    assert CATEGORY_ORDER[-1] == "Other"  # fallback bucket sorts last
