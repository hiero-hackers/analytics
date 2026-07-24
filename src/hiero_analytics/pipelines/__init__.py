"""Registry of analytics pipelines.

Each pipeline lives in this package as a module exposing a ``main()`` entry
point. The :data:`PIPELINES` registry below is the single place a pipeline
declares its name, description, CLI options, offline capability, and whether it
belongs to the default full run — the CLI (``hiero_analytics.cli``) and the
orchestrator (``hiero_analytics.pipelines.run_all``) are both driven by it.

To add a pipeline: create ``<name>.py`` here with a ``main()`` function and
append a :class:`Pipeline` entry to :data:`PIPELINES`.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Pipeline:
    """A registered analytics pipeline.

    ``name`` doubles as the module name in this package and the CLI subcommand.
    """

    name: str
    description: str
    # CLI options forwarded as keyword arguments to main(); subset of ("org", "repo").
    args: tuple[str, ...] = ()
    # Offline pipelines can rebuild their dashboard sections from durable
    # datasets; the rest need live network access and are skipped in offline
    # PR previews rather than silently making requests.
    offline: bool = False
    # Default-run pipelines execute in registry order during a full run (the
    # order CI used when they were separate steps); the others are CLI-only.
    in_default_run: bool = True

    def resolve(self) -> Callable[..., None]:
        """Import the pipeline module and return its ``main`` entry point."""
        return importlib.import_module(f"hiero_analytics.pipelines.{self.name}").main


PIPELINES: tuple[Pipeline, ...] = (
    Pipeline("difficulty", "Run repo difficulty analysis", args=("org",), offline=True),
    Pipeline("difficulty_over_time", "Run difficulty over time analysis", args=("org",), offline=True),
    Pipeline("onboarding", "Analyze repo onboarding signals", args=("org", "repo")),
    Pipeline("contributor_profiles", "Analyze contributor profiles", args=("org", "repo")),
    Pipeline("maintainer_pipeline", "Run maintainer analytics pipeline", args=("org",), offline=True),
    Pipeline("contributor_activity", "Run contributor activity analysis", args=("org",), offline=True),
    Pipeline("contributor_heatmap", "Generate contributor activity heatmaps", args=("org",), offline=True),
    Pipeline("role_coverage", "Analyze role coverage for organization", args=("org",), offline=True),
    Pipeline("affiliation", "Map contributor affiliations", args=("org",), offline=True),
    Pipeline("scorecard", "Generate scorecard metrics for an organization", args=("org",)),
    Pipeline("codeowner_and_runner", "Analyze CODEOWNERS and workflow runners", args=("org",)),
    Pipeline("hiero_hackers", "Run Hiero Hackers org analytics", args=("org",)),
    # CLI-only pipelines, excluded from the default run:
    # - dashboard: the full run renders it explicitly, last and once, after all orgs.
    # - discord_analytics: needs manual gitignored Discord CSVs (INPUTS_DIR), so it
    #   cannot run unattended in CI.
    # - contributor_churn: repo-scoped deep dive whose output no dashboard section
    #   consumes yet; flip in_default_run once one does.
    # - build_affiliations: a maintenance tool, not an analytics pipeline — it
    #   regenerates the curated affiliations.yaml source data (needs GITHUB_TOKEN
    #   and the gpg CLI), which the dashboard pipelines then read offline.
    Pipeline("dashboard", "Generate the org analytics dashboard", in_default_run=False),
    Pipeline("discord_analytics", "Run discord analysis", in_default_run=False),
    Pipeline("contributor_churn", "Analyze contributor churn", args=("org", "repo"), in_default_run=False),
    Pipeline("build_affiliations", "Regenerate the curated affiliations map from public signals", in_default_run=False),
)

PIPELINES_BY_NAME: dict[str, Pipeline] = {pipeline.name: pipeline for pipeline in PIPELINES}


def default_run_pipelines() -> list[Pipeline]:
    """Pipelines in the default full run, in execution order."""
    return [pipeline for pipeline in PIPELINES if pipeline.in_default_run]
