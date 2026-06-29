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
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from hiero_analytics.config.logging_config import setup_logging
from hiero_analytics.run_codeowner_and_runner import main as run_codeowner
from hiero_analytics.run_contributor_activity_org import main as run_contributor_activity
from hiero_analytics.run_contributor_profiles_repo import main as run_contributor_profiles
from hiero_analytics.run_difficulty_org_for_repo import main as run_difficulty
from hiero_analytics.run_difficulty_over_time_org import main as run_difficulty_over_time
from hiero_analytics.run_gfic_gfi_org import main as run_gfic
from hiero_analytics.run_hiero_hackers_org import main as run_hiero_hackers
from hiero_analytics.run_maintainer_pipeline_org import main as run_maintainer
from hiero_analytics.run_onboarding_signal_for_repo import run as run_onboarding
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
    ("contributor_activity", run_contributor_activity),
    ("maintainer_pipeline", run_maintainer),
    ("scorecard", run_scorecard),
    ("codeowner_and_runner", run_codeowner),
    ("hiero_hackers", run_hiero_hackers),
]


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


def main() -> None:
    """Configure logging once, run all pipelines, exit non-zero on any failure."""
    setup_logging()

    failures = run_pipelines(PIPELINES)

    total = len(PIPELINES)
    if failures:
        logger.error(
            "%d/%d pipelines failed: %s", len(failures), total, ", ".join(failures)
        )
        raise SystemExit(1)

    logger.info("All %d pipelines completed successfully", total)


if __name__ == "__main__":
    main()
