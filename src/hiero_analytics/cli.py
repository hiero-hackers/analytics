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
from hiero_analytics.pipelines import PIPELINES, PIPELINES_BY_NAME, run_all

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

    all_parser = subparsers.add_parser("all", help="Run the full suite of analytics pipelines (the default)")
    all_parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop after the first pipeline failure instead of continuing",
    )
    for pipeline in PIPELINES:
        subparser = subparsers.add_parser(pipeline.name, help=pipeline.description)
        for option in pipeline.args:
            subparser.add_argument(f"--{option}", help=_OPTION_HELP.get(option, f"value for --{option}"))

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the CLI."""
    args = _build_parser().parse_args(argv)
    command = args.command or "all"

    if command == "all":
        # Bare `hiero-analytics` has no --fail-fast; only the explicit `all` subcommand does.
        fail_fast = getattr(args, "fail_fast", False)
        run_all.main(fail_fast=fail_fast)  # does its own logging setup; exits non-zero on any failure
        return 0

    pipeline = PIPELINES_BY_NAME[command]
    kwargs = {option: value for option in pipeline.args if (value := getattr(args, option)) is not None}

    setup_logging()
    try:
        pipeline.resolve()(**kwargs)
    except Exception:
        logger.exception("Pipeline %s failed", command)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
