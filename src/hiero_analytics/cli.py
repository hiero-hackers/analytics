"""Command-line entry point for hiero-analytics.

``hiero-analytics`` with no arguments (or ``hiero-analytics all``) runs the full
pipeline suite; ``hiero-analytics <pipeline>`` runs a single pipeline. The
subcommands and their options come straight from the registry in
``hiero_analytics.pipelines``, so adding a pipeline there adds its subcommand.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from hiero_analytics.config.logging_config import setup_logging
from hiero_analytics.config.orgs import capabilities_of
from hiero_analytics.config.paths import ORG
from hiero_analytics.data_sources.dataset_seed import DEFAULT_SEED_REPO, SeedError, format_summary, seed_datasets
from hiero_analytics.data_sources.usage import usage_scope
from hiero_analytics.pipelines import PIPELINES, PIPELINES_BY_NAME, run_all
from hiero_analytics.pipelines._shared import api_usage_summary, shared_client

logger = logging.getLogger(__name__)

# Options a pipeline can declare via its registry entry's ``args``. Defaults stay
# None so the pipeline's own defaults (the configured GITHUB_ORG / GITHUB_REPO)
# apply unless overridden on the command line.
_OPTION_HELP = {
    "org": "GitHub organization, e.g. hiero-ledger (default: GITHUB_ORG)",
    "repo": "GitHub repository name, e.g. hiero-sdk-python (default: GITHUB_REPO)",
}


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser from the pipeline registry."""
    parser = argparse.ArgumentParser(
        prog="hiero-analytics", description="CLI for Hiero repository analytics and reporting"
    )

    subparsers = parser.add_subparsers(
        dest="command",
        title="available commands",
        description="Run `hiero-analytics <command> --help` for specific subcommand options.",
        metavar="<command>",
    )
    subparsers.add_parser("list", help="List all registered analytics pipelines")
    seed_parser = subparsers.add_parser(
        "seed-datasets",
        help="Seed outputs/data/datasets/ from the latest successful nightly snapshot, skipping the slow first fetch",
    )
    seed_parser.add_argument(
        "--repo",
        default=DEFAULT_SEED_REPO,
        help="repository whose Actions artifacts to download, OWNER/NAME (default: %(default)s; forks pass their own)",
    )
    seed_parser.add_argument(
        "--run-id",
        type=int,
        help="use this workflow run instead of the latest successful one (also allows a failed run's partial snapshot)",
    )
    seed_parser.add_argument(
        "--force",
        action="store_true",
        help="write into a datasets directory that already has files, overwriting files of the same name",
    )
    all_parser = subparsers.add_parser("all", help="Run the full suite of analytics pipelines (the default)")
    all_parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop after the first pipeline failure instead of continuing",
    )
    all_parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Exit non-zero when any organisation's pipeline fails. By default a failure confined to "
            "an extra or trial org is reported but does not fail the run"
        ),
    )
    for pipeline in PIPELINES:
        subparser = subparsers.add_parser(pipeline.name, help=pipeline.description)
        for option in pipeline.args:
            subparser.add_argument(f"--{option}", help=_OPTION_HELP.get(option, f"value for --{option}"))

    return parser


def _seed_datasets(*, repo: str, run_id: int | None, force: bool) -> int:
    """Run ``seed-datasets``: print the summary on success, a one-line error on any failure."""
    setup_logging()
    try:
        result = seed_datasets(shared_client(), repo, run_id=run_id, force=force)
    except SeedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(format_summary(result))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the CLI."""
    args = _build_parser().parse_args(argv)
    command = args.command or "all"

    if command == "all":
        # Bare `hiero-analytics` has no flags; only the explicit `all` subcommand does.
        fail_fast = getattr(args, "fail_fast", False)
        strict = getattr(args, "strict", False)
        run_all.main(fail_fast=fail_fast, strict=strict)  # does its own logging setup and exit status
        return 0

    if command == "list":
        for pipeline in PIPELINES:
            marker = " [CLI-only]" if not pipeline.in_default_run else ""
            needs = f" [requires: {', '.join(sorted(pipeline.requires))}]" if pipeline.requires else ""
            print(f"{pipeline.name:<24} {pipeline.description}{needs}{marker}")
        return 0

    if command == "seed-datasets":
        return _seed_datasets(repo=args.repo, run_id=args.run_id, force=args.force)

    pipeline = PIPELINES_BY_NAME[command]
    kwargs = {option: value for option in pipeline.args if (value := getattr(args, option)) is not None}

    setup_logging()
    target = kwargs.get("org") or ORG
    if missing := sorted(pipeline.requires - capabilities_of(target)):
        logger.warning(
            "%s needs %s, which %s's registry profile lacks; the full run would skip it for this org",
            command,
            ", ".join(missing),
            target,
        )
    try:
        # Same attribution as a full run: the org the pipeline will use (its
        # --org, else the configured one) and the pipeline's own name.
        with usage_scope(org=kwargs.get("org") or ORG, dataset=command):
            pipeline.resolve()(**kwargs)
    except Exception:
        logger.exception("Pipeline %s failed", command)
        return 1
    finally:
        total = api_usage_summary()["total"]
        logger.info(
            "GitHub API usage: %d REST request(s), %d GraphQL request(s), %d GraphQL point(s)",
            total["rest_requests"],
            total["graphql_requests"],
            total["graphql_points"],
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
