"""Assembly helpers for the dashboard-spec package.

Pure functions used by the package ``__init__`` to canonicalise each family's
chart macro and merge the per-family dicts, kept here so the ``__init__``
reads as declarative assembly only.
"""

from __future__ import annotations

from collections.abc import Sequence
from types import ModuleType

from hiero_analytics.config.orgs import has_org_overview, is_governed, is_primary


def canonical_macro(family_macro: dict) -> dict:
    """Canonicalize a family's chart macro for consumers.

    Every ``variants`` entry becomes ``(caption, [(label, chart_id), ...])``;
    family modules may write a bare chart id as sugar for a single variant.
    A chart id names the variant's dataset in the spec's ``sources`` and the
    chart document the data API writes for it.
    """
    charts = {
        org: [
            {
                **spec,
                "variants": [
                    (caption, [(caption, target)] if isinstance(target, str) else list(target))
                    for caption, target in spec["variants"]
                ],
            }
            for spec in specs
        ]
        for org, specs in family_macro["charts"].items()
    }
    return {**family_macro, "charts": charts}


def merged(families: Sequence[ModuleType], attribute: str) -> dict:
    """Merge a per-family dict keyed by chart id, failing loudly if two families claim a chart."""
    result: dict = {}
    for family in families:
        entries = getattr(family, attribute)
        overlap = result.keys() & entries.keys()
        if overlap:
            raise ValueError(f"{attribute} defined by multiple families: {sorted(overlap)}")
        result.update(entries)
    return result


def table_variants(section: dict) -> list[dict]:
    """A section's role variants as fully-resolved section dicts.

    A section without ``variants`` is its own single variant, so every consumer
    (the emitter, the metric loader, the output contract tests) can iterate one
    shape. Each declared variant inherits the section's ``file``, ``title``,
    ``description``, ``columns`` and ``periods`` and overrides what differs —
    so the variant that matches the section restates nothing, and the one that
    deviates (a differently-named count column, a differently-labelled first
    column) declares only its own difference.
    """
    declared = section.get("variants")
    if not declared:
        return [section]
    return [{**{key: value for key, value in section.items() if key != "variants"}, **variant} for variant in declared]


# Chart keys, applied in this order. ``"*"`` renders for every org; a capability
# key (``@``-prefixed) renders for orgs the registry says have that capability; a
# bare org name renders for that org alone.
WILDCARD_KEY = "*"
GOVERNED_KEY = "@governed"
ORG_OVERVIEW_KEY = "@org_overview"
PRIMARY_KEY = "@primary"


def capability_keys(org: str) -> tuple[str, ...]:
    """The capability keys ``org`` matches, in application order.

    Keyed off the org registry (:mod:`hiero_analytics.config.orgs`) rather than
    hardcoded org names, so a newly registered governed org picks up the
    governance tab's cards without a spec change.
    """
    keys = []
    if is_primary(org):
        keys.append(PRIMARY_KEY)
    if is_governed(org):
        keys.append(GOVERNED_KEY)
    if has_org_overview(org):
        keys.append(ORG_OVERVIEW_KEY)
    return tuple(keys)


def chart_specs_for_org(charts: dict, org: str) -> list[dict]:
    """A family's chart cards for ``org``, composed from every key it matches.

    Wildcard cards apply to all orgs; capability keys and the org key add extras
    on top, so an org key declares only its extras, never the wildcard list. Keys
    apply in order and an id appears once: redeclaring an id swaps its content in
    place, while a new id lands after the wildcards — so hiero-hackers' org-overview
    trails its wildcard cards rather than leading them.
    """
    ordered: dict[str, dict] = {}
    for key in (WILDCARD_KEY, *capability_keys(org), org):
        for spec in charts.get(key, []):
            ordered[spec["id"]] = spec
    return list(ordered.values())
