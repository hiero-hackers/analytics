"""Registry of analytics pipelines.

Each pipeline lives in this package as a module exposing a ``main()`` entry
point. The :data:`PIPELINES` registry below is the single place a pipeline
declares its name, description, CLI options, offline capability, and whether it
belongs to the default full run, and which org capabilities it requires — the
CLI (``hiero_analytics.cli``) and the orchestrator
(``hiero_analytics.pipelines.run_all``) are both driven by it.

To add a pipeline: create ``<name>.py`` here with a ``main()`` function and
append a :class:`Pipeline` entry to :data:`PIPELINES` (the record type lives
in ``_registry``).
"""

from __future__ import annotations

from hiero_analytics.config.orgs import DISCORD, GOVERNED, HIPS, ORG_OVERVIEW
from hiero_analytics.pipelines._registry import Pipeline

_GOVERNANCE = frozenset({GOVERNED})

PIPELINES: tuple[Pipeline, ...] = (
    # The full run executes these in order for every org it renders
    # (config.orgs.rendered_orgs), skipping a pipeline whose ``requires`` the
    # org's profile lacks. No ``requires`` means the pipeline needs nothing
    # org-specific and runs everywhere. Repo-scoped pipelines (args include
    # "repo") run for the primary org only, whose repo GITHUB_REPO names.
    Pipeline("difficulty", "Run repo difficulty analysis", args=("org",), offline=True),
    Pipeline("difficulty_over_time", "Run difficulty over time analysis", args=("org",), offline=True),
    Pipeline(
        "onboarding",
        "Analyze repo onboarding signals (writes onboarding_signal and onboarding_efficiency CSVs)",
        args=("org", "repo"),
    ),
    Pipeline("contributor_profiles", "Analyze contributor profiles", args=("org", "repo")),
    Pipeline(
        "maintainer_pipeline", "Run maintainer analytics pipeline", args=("org",), offline=True, requires=_GOVERNANCE
    ),
    Pipeline("contributor_activity", "Run contributor activity analysis", args=("org",), offline=True),
    Pipeline(
        "entity_activity",
        "Build per-repository and per-contributor activity for the detail views",
        args=("org",),
        offline=True,
    ),
    # Org-independent: labels contributors by role where the org is governed.
    Pipeline("contributor_heatmap", "Build contributor activity heatmap tables", args=("org",), offline=True),
    Pipeline(
        "role_coverage", "Analyze role coverage for organization", args=("org",), offline=True, requires=_GOVERNANCE
    ),
    Pipeline("affiliation", "Map contributor affiliations", args=("org",), offline=True, requires=_GOVERNANCE),
    Pipeline("scorecard", "Generate scorecard metrics for an organization", args=("org",)),
    Pipeline("codeowner_and_runner", "Analyze CODEOWNERS and workflow runners", args=("org",)),
    # No offline flag: plain network pipeline, skipped cleanly in offline mode
    # like scorecard/codeowner_and_runner above (see the module docstring for
    # why this isn't offline-capable like repo_growth).
    Pipeline("releases", "Fetch releases and publish cadence/staleness tables", args=("org",)),
    Pipeline(
        "ci_health",
        "Audit CI/CD workflows and repository configuration for security, reliability, and compliance",
        args=("org",),
    ),
    Pipeline(
        "org_overview",
        "Build org-overview cards (repos by contributors, language mix, recent pushes)",
        args=("org",),
        requires=frozenset({ORG_OVERVIEW}),
    ),
    # Offline runs without cached HIP datasets skip cleanly inside the pipeline
    # (the dashboard omits sections whose CSVs are absent), so it stays
    # offline-capable for PR previews.
    Pipeline(
        "hip_implementation",
        "Map HIPs to the PRs that reference them",
        args=("org",),
        offline=True,
        requires=frozenset({HIPS}),
    ),
    Pipeline("repo_growth", "Generate repos-over-time timeline tables", args=("org",), offline=True),
    # CLI-only pipelines, excluded from the default run:
    # - data_api: the full run invokes it explicitly, last and once, after all
    #   orgs — it is a re-render over every org's outputs, and its column
    #   contract should fail the run loudly if a pipeline drifts from its spec.
    # - discord_analytics: needs manual gitignored Discord CSVs (INPUTS_DIR), so it
    #   cannot run unattended in CI. Writes under the org with the discord capability.
    # - contributor_churn: repo-scoped deep dive whose output no dashboard section
    #   consumes yet; flip in_default_run once one does.
    # - build_affiliations: a maintenance tool, not an analytics pipeline — it
    #   regenerates the curated affiliations.yaml source data (needs GITHUB_TOKEN
    #   and the gpg CLI), which the analytics pipelines then read offline.
    Pipeline("data_api", "Emit the versioned JSON data API from existing outputs", in_default_run=False, offline=True),
    Pipeline("discord_analytics", "Run discord analysis", in_default_run=False, requires=frozenset({DISCORD})),
    Pipeline(
        "contributor_churn",
        "Analyze contributor churn (writes funnel, retention, transitions and tenure CSVs)",
        args=("org", "repo"),
        in_default_run=False,
    ),
    Pipeline("build_affiliations", "Regenerate the curated affiliations map from public signals", in_default_run=False),
)

PIPELINES_BY_NAME: dict[str, Pipeline] = {pipeline.name: pipeline for pipeline in PIPELINES}


def default_run_pipelines() -> list[Pipeline]:
    """Pipelines in the default full run, in execution order."""
    return [pipeline for pipeline in PIPELINES if pipeline.in_default_run]
