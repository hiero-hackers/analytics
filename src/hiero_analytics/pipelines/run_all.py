"""Run every analytics pipeline in a single process.

Sequentially invokes each default-run pipeline from the registry in
``hiero_analytics.pipelines``. Running them in one process means:

- one Python start-up instead of one cold process per pipeline, and
- a single run that reuses the on-disk fetch cache between pipelines, so org-wide
  data fetched by one pipeline is reused by the others within the run.

(Pipelines obtain their ``GitHubClient`` through ``pipelines._shared``, which
hands every pipeline in the process the same client — one HTTP session and
connection pool on top of the client module's already-shared rate limiter.)

Each pipeline is isolated: a failure is logged and the remaining pipelines still
run, and the process exits non-zero if any pipeline failed so CI surfaces it.

Multi-org: the full pipeline set runs for the primary org (``GITHUB_ORG``). Any
``GITHUB_EXTRA_ORGS`` (comma-separated) additionally get contributor-activity
only — the governance pipelines are tied to the primary org's config.yaml. The
org-aware dashboard then runs once and renders a tab per org with data.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from hiero_analytics.config.logging_config import setup_logging
from hiero_analytics.config.paths import EXTRA_ORGS
from hiero_analytics.data_sources.dataset_store import offline_mode_enabled
from hiero_analytics.pipelines import PIPELINES_BY_NAME, default_run_pipelines

logger = logging.getLogger(__name__)

# Extra orgs (config.paths.EXTRA_ORGS) get contributor-activity only — running
# the governance pipelines for an ungoverned org would produce empty role/team
# data. The dashboard (run once at the end) is org-aware and picks up every org
# that has data.


def _resolve(name: str) -> Callable[..., None]:
    """Import a registered pipeline's module and return its entry point."""
    return PIPELINES_BY_NAME[name].resolve()


def default_pipelines() -> list[tuple[str, Callable[[], None]]]:
    """(name, entry-point) pairs for the default run, resolved from the registry."""
    return [(pipeline.name, pipeline.resolve()) for pipeline in default_run_pipelines()]


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


def pipelines_for_current_mode(
    pipelines: list[tuple[str, Callable[[], None]]] | None = None,
) -> list[tuple[str, Callable[[], None]]]:
    """Return the full pipeline list, or only durable-data pipelines offline.

    Offline capability comes from each pipeline's registry entry; names not in
    the registry are treated as network-only.
    """
    available = default_pipelines() if pipelines is None else pipelines
    if not offline_mode_enabled():
        return available

    def offline_capable(name: str) -> bool:
        pipeline = PIPELINES_BY_NAME.get(name)
        return pipeline is not None and pipeline.offline

    selected = [(name, pipeline) for name, pipeline in available if offline_capable(name)]
    skipped = [name for name, _ in available if not offline_capable(name)]
    logger.info("Offline mode: skipping network-only pipelines: %s", ", ".join(skipped))
    return selected


def _run_extra_org(org: str) -> bool:
    """Run contributor-activity for an extra org in-process. Returns True on success.

    The runner takes the org as an explicit argument, so no environment mutation
    (or subprocess) is needed and the extra org shares this process's fetch cache.
    """
    logger.info("=== Extra org (contributor activity only): %s ===", org)
    try:
        _resolve("contributor_activity")(org=org)
    except Exception:
        logger.exception("Extra-org contributor activity failed for %s", org)
        return False
    return True


def main() -> None:
    """Run the primary-org pipelines, extra-org activity, then the dashboard once.

    Exits non-zero if any pipeline (or the dashboard) failed.
    """
    setup_logging()

    failures = run_pipelines(pipelines_for_current_mode())
    failures += [f"contributor_activity[{org}]" for org in EXTRA_ORGS if not _run_extra_org(org)]

    # Dashboard last, once — it renders a tab per org that has data.
    logger.info("=== Running pipeline: dashboard ===")
    try:
        _resolve("dashboard")()
    except Exception:
        logger.exception("Pipeline dashboard failed")
        failures.append("dashboard")

    if failures:
        logger.error("%d pipeline(s) failed: %s", len(failures), ", ".join(failures))
        raise SystemExit(1)

    logger.info("All pipelines completed successfully (orgs: %s)", ", ".join(["primary", *EXTRA_ORGS]))
