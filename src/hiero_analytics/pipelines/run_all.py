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
``GITHUB_EXTRA_ORGS`` (comma-separated) additionally run every org-independent
pipeline (the registry's ``extra_orgs`` flag: contributor activity, difficulty,
scorecards, codeowners) — the governance pipelines stay tied to the primary
org's config.yaml. The org-aware data API then runs once and emits a per-org
entry for every org with data, which the web dashboard renders.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from hiero_analytics.config.logging_config import setup_logging
from hiero_analytics.config.paths import DATASETS_DIR, EXTRA_ORGS
from hiero_analytics.data_sources.dataset_store import offline_mode_enabled, prune_untouched_datasets
from hiero_analytics.pipelines import PIPELINES, PIPELINES_BY_NAME, default_run_pipelines
from hiero_analytics.provenance import SNAPSHOT_MANIFEST_NAME, write_snapshot_manifest

logger = logging.getLogger(__name__)

# Extra orgs (config.paths.EXTRA_ORGS) run only the org-independent pipelines
# (registry ``extra_orgs`` flag) — running the governance pipelines for an
# ungoverned org would produce empty role/team data. The data API (run once at
# the end) is org-aware and picks up every org that has data.


def _resolve(name: str) -> Callable[..., None]:
    """Import a registered pipeline's module and return its entry point."""
    return PIPELINES_BY_NAME[name].resolve()


def default_pipelines() -> list[tuple[str, Callable[[], None]]]:
    """(name, entry-point) pairs for the default run, resolved from the registry."""
    return [(pipeline.name, pipeline.resolve()) for pipeline in default_run_pipelines()]


def run_pipelines(
    pipelines: list[tuple[str, Callable[[], None]]],
    *,
    fail_fast: bool = False,
) -> list[str]:
    """Run each pipeline, isolating failures. Returns the names that failed.

    With ``fail_fast=True``, stop after the first failure instead of continuing.
    """
    failures: list[str] = []
    for name, pipeline in pipelines:
        logger.info("=== Running pipeline: %s ===", name)
        try:
            pipeline()
        except Exception:
            if fail_fast:
                logger.exception("Pipeline %s failed; stopping due to --fail-fast", name)
                failures.append(name)
                return failures
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


def _run_extra_org(org: str) -> list[str]:
    """Run every org-independent pipeline for an extra org in-process.

    Each runner takes the org as an explicit argument, so no environment
    mutation (or subprocess) is needed and the extra org shares this process's
    fetch cache. Failures are isolated per pipeline, like the primary run;
    returns the ``name[org]`` labels of the pipelines that failed.
    """
    failures: list[str] = []
    offline = offline_mode_enabled()
    for pipeline in PIPELINES:
        if not pipeline.extra_orgs or (offline and not pipeline.offline):
            continue
        logger.info("=== Extra org %s: %s ===", org, pipeline.name)
        try:
            pipeline.resolve()(org=org)
        except Exception:
            logger.exception("Extra-org pipeline %s failed for %s", pipeline.name, org)
            failures.append(f"{pipeline.name}[{org}]")
    return failures


def main(*, fail_fast: bool = False) -> None:
    """Run the primary-org pipelines, extra-org activity, then the data API once.

    Exits non-zero if any pipeline (or the API emit) failed. With
    ``fail_fast=True``, stop after the first primary-org pipeline failure and
    skip the remaining work (extra orgs, snapshot manifest, data API).
    """
    setup_logging()

    failures = run_pipelines(pipelines_for_current_mode(), fail_fast=fail_fast)
    if fail_fast and failures:
        logger.error("%d pipeline(s) failed: %s", len(failures), ", ".join(failures))
        raise SystemExit(1)

    for extra_org in EXTRA_ORGS:
        failures += _run_extra_org(extra_org)

    # Reclaim datasets no resource claims any more, before provenance reads the
    # directory: an orphan (a fetch renamed or re-scoped, so nothing rewrites
    # its file) rides the CI cache indefinitely and drags the published
    # "data as of" back to whenever it was last written.
    #
    # Only from here, and only on a complete online run. A single-pipeline CLI
    # invocation never reaches main(); an offline run deliberately skips the
    # network pipelines, so most datasets go unclaimed; and a failed pipeline
    # may simply not have got as far as its fetch. In each of those the
    # unclaimed set is an artefact of the run, not evidence of an orphan.
    if failures:
        logger.info("Skipping the dataset prune: %d pipeline(s) failed, so unclaimed != orphaned", len(failures))
    elif offline_mode_enabled():
        logger.info("Skipping the dataset prune: offline runs do not claim the network-backed datasets")
    else:
        prune_untouched_datasets()

    # Describe the snapshot before the data API emits against it. Written
    # even when pipelines failed — a partial run still produces charts, and the
    # manifest's failure list is what tells a later reader the snapshot the
    # archive holds is incomplete.
    #
    # A missing manifest is a run failure, not a warning: without it the archived
    # datasets carry no hashes, watermarks, or failure list, so the charts this
    # run publishes cannot be traced to their inputs. Recorded as a failure
    # rather than raised so the API is still emitted for inspection — the
    # non-zero exit then keeps the Pages deploy (which needs this job) from
    # publishing untraceable output.
    try:
        write_snapshot_manifest(DATASETS_DIR / SNAPSHOT_MANIFEST_NAME, failures=failures)
    except Exception:
        logger.exception("Could not write the snapshot manifest")
        failures.append("snapshot_manifest")

    # The data API last, once — a re-render over everything above, emitting a
    # per-org entry for every org that has data. Its column contract fails the
    # run loudly if any pipeline drifted from its dashboard spec.
    logger.info("=== Running pipeline: data_api ===")
    try:
        _resolve("data_api")()
    except Exception:
        logger.exception("Pipeline data_api failed")
        failures.append("data_api")

    if failures:
        logger.error("%d pipeline(s) failed: %s", len(failures), ", ".join(failures))
        raise SystemExit(1)

    logger.info("All pipelines completed successfully (orgs: %s)", ", ".join(["primary", *EXTRA_ORGS]))
