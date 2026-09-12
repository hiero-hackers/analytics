"""Registry of analytics pipelines.

Each pipeline lives in this package as a module exposing a ``main()`` entry
point. The :data:`PIPELINES` registry below is the single place a pipeline
declares its name, description, CLI options, offline capability, and whether it
belongs to the default full run — the CLI (``hiero_analytics.cli``) and the
orchestrator (``hiero_analytics.pipelines.run_all``) are both driven by it.

To add a pipeline: create ``<name>.py`` here with a ``main()`` function and
append a :class:`Pipeline` entry to :data:`PIPELINES` (the record type lives
in ``_registry``).
"""

from __future__ import annotations

from hiero_analytics.pipelines._registry import Pipeline

PIPELINES: tuple[Pipeline, ...] = (
    # extra_orgs marks the org-independent pipelines: they need no governance
    # config, so the full run repeats them for each EXTRA_ORGS org and the
    # per-org dashboard fills in wherever data can exist. The governance-shaped
    # pipelines (roles, teams, affiliations, HIPs) stay primary-org only, and
    # onboarding/contributor_profiles are repo-scoped rather than org-scoped.
    Pipeline("difficulty", "Run repo difficulty analysis", args=("org",), offline=True, extra_orgs=True),
    Pipeline("difficulty_over_time", "Run difficulty over time analysis", args=("org",), offline=True, extra_orgs=True),
    Pipeline("onboarding", "Analyze repo onboarding signals", args=("org", "repo")),
    Pipeline("contributor_profiles", "Analyze contributor profiles", args=("org", "repo")),
    Pipeline("maintainer_pipeline", "Run maintainer analytics pipeline", args=("org",), offline=True),
    Pipeline("contributor_activity", "Run contributor activity analysis", args=("org",), offline=True, extra_orgs=True),
    Pipeline("contributor_heatmap", "Generate contributor activity heatmaps", args=("org",), offline=True),
    Pipeline("role_coverage", "Analyze role coverage for organization", args=("org",), offline=True),
    Pipeline("affiliation", "Map contributor affiliations", args=("org",), offline=True),
    Pipeline("scorecard", "Generate scorecard metrics for an organization", args=("org",), extra_orgs=True),
    Pipeline("codeowner_and_runner", "Analyze CODEOWNERS and workflow runners", args=("org",), extra_orgs=True),
    Pipeline(
        "ci_health",
        "Audit CI/CD workflows and repository configuration for security, reliability, and compliance",
        args=("org",),
        extra_orgs=True,
    ),
    Pipeline("hiero_hackers", "Run Hiero Hackers org analytics", args=("org",)),
    # Offline runs without cached HIP datasets skip cleanly inside the pipeline
    # (the dashboard omits sections whose CSVs are absent), so it stays
    # offline-capable for PR previews.
    Pipeline("hip_implementation", "Map HIPs to the PRs that reference them", args=("org",), offline=True),
    Pipeline("repo_growth", "Generate repos-over-time timeline charts", args=("org",), offline=True, extra_orgs=True),
    # CLI-only pipelines, excluded from the default run:
    # - data_api: the full run invokes it explicitly, last and once, after all
    #   orgs — it is a re-render over every org's outputs, and its column
    #   contract should fail the run loudly if a pipeline drifts from its spec.
    # - discord_analytics: needs manual gitignored Discord CSVs (INPUTS_DIR), so it
    #   cannot run unattended in CI.
    # - contributor_churn: repo-scoped deep dive whose output no dashboard section
    #   consumes yet; flip in_default_run once one does.
    # - build_affiliations: a maintenance tool, not an analytics pipeline — it
    #   regenerates the curated affiliations.yaml source data (needs GITHUB_TOKEN
    #   and the gpg CLI), which the analytics pipelines then read offline.
    Pipeline("data_api", "Emit the versioned JSON data API from existing outputs", in_default_run=False, offline=True),
    Pipeline("discord_analytics", "Run discord analysis", in_default_run=False),
    Pipeline("contributor_churn", "Analyze contributor churn", args=("org", "repo"), in_default_run=False),
    Pipeline("build_affiliations", "Regenerate the curated affiliations map from public signals", in_default_run=False),
)

PIPELINES_BY_NAME: dict[str, Pipeline] = {pipeline.name: pipeline for pipeline in PIPELINES}


def default_run_pipelines() -> list[Pipeline]:
    """Pipelines in the default full run, in execution order."""
    return [pipeline for pipeline in PIPELINES if pipeline.in_default_run]
