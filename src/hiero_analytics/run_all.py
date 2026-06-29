"""Run every analytics pipeline in a single process.

Sequentially invokes each pipeline's entry point in the same order the CI
workflow used to run them as separate steps. Running them in one process means:

- one Python start-up instead of one cold process per pipeline, and
- a single run that reuses the on-disk fetch cache between pipelines, so org-wide
  data fetched by one pipeline is reused by the others within the run.

(Each pipeline still constructs its own ``GitHubClient``; there is no shared HTTP
session today. Injecting a shared client would be a further optimization.)

Each pipeline is isolated: a failure is logged and the remaining pipelines still
run, and the process exits non-zero if any pipeline failed so CI surfaces it.

Multi-org: the full pipeline set runs for the primary org (``GITHUB_ORG``). Any
``GITHUB_EXTRA_ORGS`` (comma-separated) additionally get contributor-activity
only — the governance pipelines are tied to the primary org's config.yaml. The
org-aware dashboard then runs once and renders a tab per org with data.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from collections.abc import Callable

from hiero_analytics.config.logging_config import setup_logging
from hiero_analytics.run_codeowner_and_runner import main as run_codeowner
from hiero_analytics.run_contributor_activity_org import main as run_contributor_activity
from hiero_analytics.run_contributor_heatmap_org import main as run_contributor_heatmap
from hiero_analytics.run_contributor_profiles_repo import main as run_contributor_profiles
from hiero_analytics.run_dashboard import main as run_dashboard
from hiero_analytics.run_difficulty_org_for_repo import main as run_difficulty
from hiero_analytics.run_difficulty_over_time_org import main as run_difficulty_over_time
from hiero_analytics.run_gfic_gfi_org import main as run_gfic
from hiero_analytics.run_hiero_hackers_org import main as run_hiero_hackers
from hiero_analytics.run_maintainer_pipeline_org import main as run_maintainer
from hiero_analytics.run_onboarding_signal_for_repo import run as run_onboarding
from hiero_analytics.run_role_coverage_org import main as run_role_coverage
from hiero_analytics.run_scorecard_for_org import main as run_scorecard

logger = logging.getLogger(__name__)

# (name, entry-point) in CI execution order. Only run_hiero_discord_analytics is
# intentionally excluded: it needs manual gitignored Discord CSVs (INPUTS_DIR) and
# cannot run unattended in CI. Add it here only if CI gains the required inputs.
PIPELINES: list[tuple[str, Callable[[], None]]] = [
    ("gfic_gfi", run_gfic),
    ("difficulty", run_difficulty),
    ("difficulty_over_time", run_difficulty_over_time),
    ("onboarding", run_onboarding),
    ("contributor_profiles", run_contributor_profiles),
    ("maintainer_pipeline", run_maintainer),
    ("contributor_activity", run_contributor_activity),
    ("contributor_heatmap", run_contributor_heatmap),
    ("role_coverage", run_role_coverage),
    ("scorecard", run_scorecard),
    ("codeowner_and_runner", run_codeowner),
    ("hiero_hackers", run_hiero_hackers),
]

# Extra orgs (comma-separated) get contributor-activity only — the governance
# pipelines above are tied to the primary org's config.yaml, so running them for
# an org without one would produce misleading role/team data. The dashboard
# (run once at the end) is org-aware and picks up every org that has data.
EXTRA_ORGS = [org.strip() for org in os.getenv("GITHUB_EXTRA_ORGS", "").split(",") if org.strip()]


def run_pipelines(pipelines: list[tuple[str, Callable[[], None]]]) -> list[str]:
    """Run each pipeline, isolating failures. Returns the names that failed."""
    failures: list[str] = []
    for name, pipeline in pipelines:
        logger.info("=== Running pipeline: %s ===", name)
        try:
            pipeline()
        except Exception:
            logger.exception("Pipeline %s failed; continuing with the rest", name)
            failures.append(name)
    return failures


def _run_extra_org(org: str) -> bool:
    """Run contributor-activity for an extra org in a subprocess (clean GITHUB_ORG).

    A subprocess is used so the org is resolved at import time for that run,
    without mutating this process's configuration. Returns True on success.
    """
    logger.info("=== Extra org (contributor activity only): %s ===", org)
    result = subprocess.run(
        [sys.executable, "-m", "hiero_analytics.run_contributor_activity_org"],
        env={**os.environ, "GITHUB_ORG": org},
        check=False,
    )
    if result.returncode != 0:
        logger.error("Extra-org contributor activity failed for %s", org)
    return result.returncode == 0


def main() -> None:
    """Run the primary-org pipelines, extra-org activity, then the dashboard once.

    Exits non-zero if any pipeline (or the dashboard) failed.
    """
    setup_logging()

    failures = run_pipelines(PIPELINES)
    failures += [f"contributor_activity[{org}]" for org in EXTRA_ORGS if not _run_extra_org(org)]

    # Dashboard last, once — it renders a tab per org that has data.
    logger.info("=== Running pipeline: dashboard ===")
    try:
        run_dashboard()
    except Exception:
        logger.exception("Pipeline dashboard failed")
        failures.append("dashboard")

    if failures:
        logger.error("%d pipeline(s) failed: %s", len(failures), ", ".join(failures))
        raise SystemExit(1)

    logger.info("All pipelines completed successfully (orgs: %s)", ", ".join(["primary", *EXTRA_ORGS]))


if __name__ == "__main__":
    main()
