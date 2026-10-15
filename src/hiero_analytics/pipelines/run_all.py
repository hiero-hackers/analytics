"""Run every analytics pipeline, for every organisation, in a single process.

Running everything in one process means one Python start-up instead of one
cold process per pipeline, and a run that reuses the on-disk fetch cache
between pipelines, so org-wide data fetched by one pipeline is reused by the
others. (Pipelines obtain their ``GitHubClient`` through ``pipelines._shared``,
which hands every pipeline in the process the same client.)

Multi-org: the run renders every org ``config.orgs.rendered_orgs()`` lists —
the primary org, the registry's extra orgs, and any trial orgs — and for each
one executes every default-run pipeline whose ``requires`` the org's profile
satisfies (``config.orgs.capabilities_of``). A governed extra org therefore
gets the governance pipelines; an ungoverned one gets the org-independent set.
Repo-scoped pipelines run for the primary org only. The org-aware data API then
runs once and emits a per-org entry for every org with data.

Failure policy: each pipeline is isolated, so a failure is logged and the rest
still run. The process exits non-zero when anything in the *primary* org fails,
or the snapshot manifest or the data API fails — the scheduled workflow then
keeps the last good deploy. A failure confined to an extra or trial org is
recorded in ``SNAPSHOT.json`` and the Actions job summary, and does not fail
the run: one small org's outage must not hold every org's dashboard back.
``strict=True`` (``hiero-analytics all --strict``, used by PR previews) fails
on any failure instead.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path

from hiero_analytics.config import orgs as org_registry
from hiero_analytics.config import paths
from hiero_analytics.config.logging_config import setup_logging
from hiero_analytics.data_sources.dataset_store import offline_mode_enabled, prune_untouched_datasets
from hiero_analytics.data_sources.github_ingest import fetch_org_login
from hiero_analytics.data_sources.usage import render_usage_markdown, usage_scope
from hiero_analytics.pipelines import PIPELINES_BY_NAME, default_run_pipelines
from hiero_analytics.pipelines._registry import Pipeline
from hiero_analytics.pipelines._shared import api_usage_summary, reset_api_usage, shared_client
from hiero_analytics.provenance import SNAPSHOT_MANIFEST_NAME, write_snapshot_manifest

logger = logging.getLogger(__name__)


def _resolve(name: str) -> Callable[..., None]:
    """Import a registered pipeline's module and return its entry point."""
    return PIPELINES_BY_NAME[name].resolve()


def _rendered_orgs() -> list[str]:
    """The orgs this run renders, primary first (indirection for tests)."""
    return org_registry.rendered_orgs()


def failure_label(pipeline: str, org: str, *, primary: bool) -> str:
    """How a failure is named: bare for the primary org, ``name[org]`` otherwise."""
    return pipeline if primary else f"{pipeline}[{org}]"


def is_org_scoped_failure(label: str) -> bool:
    """Whether a failure label belongs to an extra or trial org (``name[org]``)."""
    return label.endswith("]") and "[" in label


def failed_orgs(failures: list[str]) -> set[str]:
    """The extra or trial orgs named in ``name[org]`` failure labels."""
    return {label[label.index("[") + 1 : -1] for label in failures if is_org_scoped_failure(label)}


def _belongs_to_any(orgs: set[str]) -> Callable[[Path], bool]:
    """A predicate: is this dataset file one of these orgs' (``<resource>_<org>_<fingerprint>.json``)?"""
    slugs = [f"_{org.replace('/', '_')}_" for org in orgs]
    return lambda path: any(slug in path.name for slug in slugs)


def pipelines_for(org: str, *, primary: bool) -> list[Pipeline]:
    """The default-run pipelines that apply to ``org``, in registry order.

    A pipeline applies when the org's profile has every capability it
    requires; repo-scoped pipelines apply to the primary org only; offline
    runs keep only pipelines that can rebuild from durable datasets.
    """
    capabilities = org_registry.capabilities_of(org)
    offline = offline_mode_enabled()
    selected: list[Pipeline] = []
    skipped_offline: list[str] = []
    for pipeline in default_run_pipelines():
        if pipeline.repo_scoped and not primary:
            continue
        if not pipeline.requires <= capabilities:
            continue
        if offline and not pipeline.offline:
            skipped_offline.append(pipeline.name)
            continue
        selected.append(pipeline)
    if skipped_offline:
        logger.info("Offline mode: skipping network-only pipelines for %s: %s", org, ", ".join(skipped_offline))
    return selected


def _has_cached_datasets(org: str) -> bool:
    """Whether any persisted dataset exists for ``org`` (read at call time for tests)."""
    directory = paths.DATASETS_DIR
    if not directory.is_dir():
        return False
    slug = org.replace("/", "_")
    return any(directory.glob(f"*_{slug}_*.json"))


def preflight_org(org: str) -> str | None:
    """Check ``org`` exists on GitHub under exactly this spelling; a problem description or None.

    Costs one GraphQL point. Skipped offline. Every output path and every
    ``owner/repo`` join is keyed on the exact login, while GitHub matches logins
    case-insensitively and returns its own casing in repository names — so a
    registry entry spelt ``lfdt-clpr`` for ``LFDT-CLPR`` would fetch fine and
    then silently fail to join. Better to stop that org before it fetches.

    Only a definite answer stops an org: GitHub says it does not exist, or
    spells it differently. A lookup that itself fails (a network blip, a 5xx)
    is logged and the org runs anyway, since skipping it would drop it from that
    night's dashboard over an error its own pipelines may well ride out.
    """
    if offline_mode_enabled():
        return None
    with usage_scope(org=org, dataset="preflight"):
        try:
            login = fetch_org_login(shared_client(), org)
        except Exception as exc:  # a failed lookup is not evidence about the org
            logger.warning("Could not check organisation %r on GitHub (%s); running it anyway", org, exc)
            return None
    if login is None:
        return f"organisation {org!r} does not exist on GitHub (or the token cannot see it)"
    if login != org:
        return (
            f"organisation {org!r} is spelt {login!r} on GitHub; paths and joins are case-sensitive, "
            "so register it with GitHub's spelling"
        )
    return None


def run_org(org: str, *, primary: bool, fail_fast: bool = False) -> list[str]:
    """Run every applicable pipeline for ``org``, isolating failures; the failed labels.

    Each pipeline receives the org explicitly (no environment mutation), runs
    under the ``(org, pipeline)`` usage scope, and shares this process's client
    and fetch cache. With ``fail_fast``, stops at the first failure.
    """
    if not primary and offline_mode_enabled() and not _has_cached_datasets(org):
        logger.warning("Offline mode: no cached datasets for %s yet; skipping it (a live run will fetch them)", org)
        return []

    if problem := preflight_org(org):
        logger.error("Skipping %s: %s", org, problem)
        return [failure_label("preflight", org, primary=primary)]

    failures: list[str] = []
    for pipeline in pipelines_for(org, primary=primary):
        logger.info("=== %s: %s ===", org, pipeline.name)
        try:
            # Requests a pipeline makes outside a persisted dataset fetch are
            # attributed to the pipeline itself; dataset fetches narrow this.
            with usage_scope(org=org, dataset=pipeline.name):
                entry = pipeline.resolve()
                if "org" in pipeline.args:
                    entry(org=org)
                else:
                    entry()
        except Exception:
            label = failure_label(pipeline.name, org, primary=primary)
            failures.append(label)
            if fail_fast:
                logger.exception("Pipeline %s failed; stopping due to --fail-fast", label)
                return failures
            logger.exception("Pipeline %s failed; continuing with the rest", label)
    return failures


def _append_step_summary(markdown: str) -> None:
    """Append to the Actions job summary, when running in Actions.

    ``GITHUB_STEP_SUMMARY`` names a file Actions renders on the run page; outside
    Actions it is unset and this does nothing. A summary is a convenience, so a
    failure to write it is logged rather than failing a run that otherwise worked.
    """
    target = os.getenv("GITHUB_STEP_SUMMARY", "").strip()
    if not target:
        return
    try:
        with Path(target).open("a", encoding="utf-8") as handle:
            handle.write(markdown)
    except OSError:
        logger.warning("Could not write the job summary to %s", target, exc_info=True)


def _write_usage_step_summary(api_usage: dict) -> None:
    """Append the API usage table to the Actions job summary."""
    _append_step_summary(render_usage_markdown(api_usage))


def render_failures_markdown(failures: list[str], *, tolerated: bool) -> str:
    """The run's pipeline failures as a Markdown section for the job summary."""
    if not failures:
        return ""
    lines = ["## Pipeline failures", ""]
    if tolerated:
        lines += [
            (
                "These failures are confined to extra or trial organisations, so the run still "
                "published. The sections these pipelines feed are missing for the affected "
                "organisations until a later run succeeds; their datasets keep their watermarks, "
                "so that run resumes where this one stopped."
            ),
            "",
        ]
    lines += [f"- `{label}`" for label in failures]
    if any(label.startswith("preflight") for label in failures):
        lines += [
            "",
            (
                "A `preflight` failure means GitHub has no organisation by that exact spelling, so "
                "the organisation was skipped entirely and is absent from this deploy."
            ),
        ]
    return "\n".join(lines) + "\n\n"


def _annotate(message: str) -> None:
    """Raise a warning annotation on the Actions run page (stdout workflow command)."""
    if os.getenv("GITHUB_ACTIONS"):
        print(f"::warning title=Analytics pipelines::{message}")  # an Actions workflow command


def main(*, fail_fast: bool = False, strict: bool = False) -> None:
    """Run every org's pipelines, then the data API once.

    Exits non-zero when a primary-org pipeline, the snapshot manifest or the
    data API failed, or — with ``strict`` — when anything failed. With
    ``fail_fast``, stops at the first failure anywhere and skips the remaining
    work (later orgs, snapshot manifest, data API).
    """
    setup_logging()
    reset_api_usage()  # each run reports only its own spend

    orgs = _rendered_orgs()
    logger.info("Rendering %d org(s): %s", len(orgs), ", ".join(orgs))
    failures: list[str] = []
    for index, org in enumerate(orgs):
        failures += run_org(org, primary=index == 0, fail_fast=fail_fast)
        if fail_fast and failures:
            # The manifest is skipped on this path, but the budget was still spent.
            _write_usage_step_summary(api_usage_summary())
            logger.error("%d pipeline(s) failed: %s", len(failures), ", ".join(failures))
            raise SystemExit(1)

    # Reclaim datasets no resource claims any more, before provenance reads the
    # directory: an orphan (a fetch renamed or re-scoped, so nothing rewrites
    # its file) rides the CI cache indefinitely and drags the published
    # "data as of" back to whenever it was last written.
    #
    # Only from here, and only on an online run whose primary org completed. A
    # single-pipeline CLI invocation never reaches main(); an offline run
    # deliberately skips the network pipelines, so most datasets go unclaimed;
    # and a failed pipeline may simply not have got as far as its fetch. In each
    # of those the unclaimed set is an artefact of the run, not evidence of an
    # orphan. Failures confined to extra orgs no longer skip the prune (that
    # would let orphans, such as a past trial org's datasets, ride the cache and
    # age the published "data as of"); instead those orgs' own datasets are kept.
    primary_failures = [label for label in failures if not is_org_scoped_failure(label)]
    if primary_failures:
        logger.info(
            "Skipping the dataset prune: %d primary-org pipeline(s) failed, so unclaimed != orphaned",
            len(primary_failures),
        )
    elif offline_mode_enabled():
        logger.info("Skipping the dataset prune: offline runs do not claim the network-backed datasets")
    else:
        prune_untouched_datasets(keep=_belongs_to_any(failed_orgs(failures)))

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
    #
    # The run's API spend rides in the same manifest, and the job summary renders
    # that same dict, so the two cannot disagree.
    api_usage = api_usage_summary()
    try:
        write_snapshot_manifest(
            paths.DATASETS_DIR / SNAPSHOT_MANIFEST_NAME, failures=list(failures), api_usage=api_usage
        )
    except Exception:
        logger.exception("Could not write the snapshot manifest")
        failures.append("snapshot_manifest")

    # The data API last, once — a re-render over everything above, emitting a
    # per-org entry for every org that has data. Its column contract fails the
    # run loudly if any pipeline drifted from its dashboard spec.
    logger.info("=== Running pipeline: data_api ===")
    try:
        with usage_scope(dataset="data_api"):
            _resolve("data_api")()
    except Exception:
        logger.exception("Pipeline data_api failed")
        failures.append("data_api")

    blocking = [label for label in failures if strict or not is_org_scoped_failure(label)]
    tolerated = [label for label in failures if label not in blocking]

    # The very dict the manifest recorded, so the job summary and the archived
    # SNAPSHOT.json report identical figures. (The data API re-renders local
    # datasets and makes no GitHub requests of its own.)
    _write_usage_step_summary(api_usage)
    _append_step_summary(render_failures_markdown(failures, tolerated=not blocking))

    if blocking:
        logger.error("%d pipeline(s) failed: %s", len(failures), ", ".join(failures))
        raise SystemExit(1)
    if tolerated:
        message = (
            f"{len(tolerated)} pipeline(s) failed for extra or trial orgs; published anyway: {', '.join(tolerated)}"
        )
        logger.warning(message)
        _annotate(message)
        return

    logger.info("All pipelines completed successfully (orgs: %s)", ", ".join(orgs))
