"""Tests for semantic repository categorization."""

from __future__ import annotations

from hiero_analytics.domain.repo_categories import CATEGORY_ORDER, REPO_CATEGORIES, categorize_repo


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


def test_overrides_win_over_the_curated_map_and_keyword_rules():
    """Per-org overrides (from the org registry) are checked first, by bare name."""
    overrides = {"analytics": "Tooling / DevEx", "hiero-sdk-python": "Docs / Web"}

    assert categorize_repo("hiero-hackers/analytics", overrides) == "Tooling / DevEx"
    assert categorize_repo("hiero-sdk-python", overrides) == "Docs / Web"
    # Without overrides the curated map and keyword rules apply as before.
    assert categorize_repo("analytics") == "Other"
    assert categorize_repo("hiero-sdk-python") == "SDKs"


def test_domain_does_not_depend_on_config():
    """The layer rule (docs/architecture.md): domain imports nothing from config."""
    import ast
    from pathlib import Path

    import hiero_analytics.domain.repos as repos

    for path in Path(repos.__file__).parent.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("hiero_analytics.config"), f"{path.name} imports {node.module}"
