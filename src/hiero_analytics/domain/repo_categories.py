"""Semantic categories for Hiero repositories — what a repo *is*, not who maintains it.

A curated ``repo -> category`` map with an ordered keyword fallback, so new repos
(e.g. a future ``hiero-sdk-kotlin``) land in a sensible bucket automatically. Used
to colour the maintainer network and reusable for any other per-repo grouping.
"""

from __future__ import annotations

from collections.abc import Mapping

from hiero_analytics.domain.repos import bare_repo

# Curated map. Keys are bare repo names (the part after the last '/'), lowercased.
REPO_CATEGORIES = {
    # SDKs
    "hiero-sdk-js": "SDKs",
    "hiero-sdk-java": "SDKs",
    "hiero-sdk-python": "SDKs",
    "hiero-sdk-rust": "SDKs",
    "hiero-sdk-cpp": "SDKs",
    "hiero-sdk-go": "SDKs",
    "hiero-sdk-swift": "SDKs",
    "hiero-sdk-tck": "SDKs",
    "sdk-collaboration-hub": "SDKs",
    # Identity / DID
    "hiero-did-sdk-js": "Identity / DID",
    "hiero-did-sdk-python": "Identity / DID",
    "identity-collaboration-hub": "Identity / DID",
    "heka-identity-platform": "Identity / DID",
    # Core network
    "hiero-consensus-node": "Core network",
    "hiero-block-node": "Core network",
    "hiero-mirror-node": "Core network",
    "hiero-mirror-node-explorer": "Core network",
    "hiero-consensus-specifications": "Core network",
    "hiero-cryptography": "Core network",
    # EVM / smart contracts
    "hiero-contracts": "EVM / smart contracts",
    "hiero-ethereum-execution-spec-tests": "EVM / smart contracts",
    "hiero-json-rpc-relay": "EVM / smart contracts",
    "hiero-hederium": "EVM / smart contracts",
    # Tooling / DevEx
    "solo": "Tooling / DevEx",
    "solo-docs": "Tooling / DevEx",
    "hiero-solo-action": "Tooling / DevEx",
    "hiero-cli": "Tooling / DevEx",
    "hiero-local-node": "Tooling / DevEx",
    "hiero-gradle-conventions": "Tooling / DevEx",
    "homebrew-tools": "Tooling / DevEx",
    # Governance
    "governance": "Governance",
    "tsc": "Governance",
    "tsc-eligibility-check": "Governance",
    "hiero-improvement-proposals": "Governance",
    ".github": "Governance",
    # Docs / Web
    "hiero-docs": "Docs / Web",
    "hiero-website": "Docs / Web",
    # Apps / Integrations
    "hiero-enterprise-java": "Apps / Integrations",
    "hiero-enterprise-js": "Apps / Integrations",
    "hiero-enterprise-proxy": "Apps / Integrations",
}

# Stable display / colour order; "Other" is the fallback bucket, shown last.
CATEGORY_ORDER = [
    "SDKs",
    "Identity / DID",
    "Core network",
    "EVM / smart contracts",
    "Tooling / DevEx",
    "Governance",
    "Docs / Web",
    "Apps / Integrations",
    "Other",
]

# Ordered substring rules for repos not in the curated map (first match wins).
# Order matters: more specific terms come before broader ones (e.g. did before sdk).
_KEYWORD_RULES = [
    ("did", "Identity / DID"),
    ("identity", "Identity / DID"),
    ("enterprise", "Apps / Integrations"),
    ("sdk", "SDKs"),
    ("consensus", "Core network"),
    ("mirror", "Core network"),
    ("block-node", "Core network"),
    ("crypto", "Core network"),
    ("contract", "EVM / smart contracts"),
    ("json-rpc", "EVM / smart contracts"),
    ("execution-spec", "EVM / smart contracts"),
    ("evm", "EVM / smart contracts"),
    ("solo", "Tooling / DevEx"),
    ("cli", "Tooling / DevEx"),
    ("local-node", "Tooling / DevEx"),
    ("gradle", "Tooling / DevEx"),
    ("homebrew", "Tooling / DevEx"),
    ("tools", "Tooling / DevEx"),
    ("governance", "Governance"),
    ("tsc", "Governance"),
    ("improvement-proposal", "Governance"),
    ("docs", "Docs / Web"),
    ("website", "Docs / Web"),
]


def categorize_repo(repo: str, overrides: Mapping[str, str] | None = None) -> str:
    """Map a repository (``owner/name`` or bare name) to a semantic category.

    Checks ``overrides`` first (bare name -> category; callers pass the org
    registry's ``repo_category_overrides()``, so per-org knowledge stays with
    the org), then the curated map, then the ordered keyword rules, else
    ``"Other"``. Taking the overrides as an argument keeps ``domain`` free of
    any dependency on ``config``.
    """
    name = bare_repo(str(repo)).lower()
    if overrides and name in overrides:
        return overrides[name]
    if name in REPO_CATEGORIES:
        return REPO_CATEGORIES[name]
    for keyword, category in _KEYWORD_RULES:
        if keyword in name:
            return category
    return "Other"
