"""CLI entrypoint for hiero-analytics."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from hiero_analytics.config.logging_config import setup_logging


@dataclass
class Argument:
    """Dataclass represnting a argument."""

    name: str | None = None
    dest: str | None = None
    metavar: str = ""
    description: str | None = None
    type: type | None = None
    default_value: any | None = None


@dataclass
class Command:
    """Dataclass representing a command."""

    name: str | None = None
    description: str | None = None
    args: list[Argument] = field(default_factory=list)
    func: Callable | None = None


ARGUMENTS: dict[str, Argument] = {
    "org": Argument(
        name="--org",
        description="Github organization name eg.hiero-ledger",
        dest="org",
        default_value="hiero-ledger",
        type=str,
    ),
    "repo": Argument(
        name="--repo",
        description="Github repository name eg.hiero-sdk-python",
        dest="repo",
        default_value="hiero-sdk-python",
        type=str,
    ),
}


COMMANDS: list[Command] = [
    Command(
        name="all",
        description="Run the full suite of analytics pipelines",
        func=lambda _: __import__("hiero_analytics.run_all", fromlist=["main"]).main(),
    ),
    Command(
        name="scorecard",
        description="Generate scorecard metrics for an organization",
        args=[ARGUMENTS["org"]],
        func=lambda args: __import__("hiero_analytics.run_scorecard_for_org", fromlist=["main"]).main(args.org),
    ),
    Command(
        name="dashboard",
        description="Generate the org analytics dashboard",
        func=lambda _: __import__("hiero_analytics.run_dashboard", fromlist=["main"]).main(),
    ),
    Command(
        name="onboarding",
        description="Analyze repo onboarding signals",
        args=[ARGUMENTS["org"], ARGUMENTS["repo"]],
        func=lambda args: __import__("hiero_analytics.run_onboarding_signal_for_repo", fromlist=["run"]).run(
            args.org, args.repo
        ),
    ),
    Command(
        name="maintainer",
        description="Run maintainer analytics pipeline",
        args=[ARGUMENTS["org"]],
        func=lambda args: __import__("hiero_analytics.run_maintainer_pipeline_org", fromlist=["main"]).main(args.org),
    ),
    Command(
        name="roles",
        description="Analyze role coverage for organization",
        func=lambda _: __import__("hiero_analytics.run_role_coverage_org", fromlist=["main"]).main(),
    ),
    Command(
        name="affiliation",
        description="Map contributor affiliations",
        func=lambda _: __import__("hiero_analytics.run_affiliation_org", fromlist=["main"]).main(),
    ),
    Command(
        name="codeowners",
        description="Analyze CODEOWNERS and workflow runners",
        func=lambda _: __import__("hiero_analytics.run_codeowner_and_runner", fromlist=["main"]).main(),
    ),
    Command(
        name="activity",
        description="Run contributor activity analysis",
        args=[ARGUMENTS["org"]],
        func=lambda args: __import__("hiero_analytics.run_contributor_activity_org", fromlist=["main"]).main(args.org),
    ),
    Command(
        name="heatmap",
        description="Generate contributor activity heatmaps",
        func=lambda _: __import__("hiero_analytics.run_contributor_heatmap_org", fromlist=["main"]).main(),
    ),
    Command(
        name="profiles",
        description="Analyze contributor profiles",
        args=[ARGUMENTS["org"], ARGUMENTS["repo"]],
        func=lambda args: __import__("hiero_analytics.run_contributor_profiles_repo", fromlist=["main"]).main(
            args.org, args.repo
        ),
    ),
    Command(
        name="difficulty",
        description="Run repo difficulty analysis",
        args=[ARGUMENTS["org"]],
        func=lambda args: __import__("hiero_analytics.run_difficulty_org_for_repo", fromlist=["main"]).main(args.org),
    ),
    Command(
        name="difficulty-time",
        description="Run difficulty over time analysis",
        args=[ARGUMENTS["org"]],
        func=lambda args: __import__("hiero_analytics.run_difficulty_over_time_org", fromlist=["main"]).main(args.org),
    ),
    Command(
        name="discord",
        description="Run discord analysis",
        func=lambda _: __import__("hiero_analytics.run_hiero_discord_analytics", fromlist=["main"]).main(),
    ),
    Command(
        name="hackers",
        description="Run Hiero Hackers org analytics",
        func=lambda _: __import__("hiero_analytics.run_hiero_hackers_org", fromlist=["main"]).main(),
    ),
    Command(
        name="churn",
        description="Analyze contributor churn",
        args=[ARGUMENTS["org"], ARGUMENTS["repo"]],
        func=lambda args: __import__("hiero_analytics.run_contributor_churn_analysis", fromlist=["run"]).run(
            args.org, args.repo
        ),
    ),
]


def _build_parser() -> argparse.ArgumentParser:
    """Build the ArgumnetParser for the Commands."""
    parser = argparse.ArgumentParser(
        prog="hiero-analytics", description="CLI for Hiero repository analytics and reporting"
    )

    subparsers = parser.add_subparsers(
        dest="command",
        title="available commands",
        description="Run `hiero-analytics <command> --help` for specific subcommand options.",
        metavar="<command>",
    )

    for command in COMMANDS:
        command_parser = subparsers.add_parser(command.name, help=command.description)
        command_parser.set_defaults(func=command.func)

        for arg in command.args:
            command_parser.add_argument(
                arg.name,
                metavar=arg.metavar,
                default=arg.default_value,
                dest=arg.dest,
                help=arg.description,
            )

    return parser


def main(argv: Sequence[str] | None = None):
    """Entry point for the CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    try:
        setup_logging()
        args.func(args)
        return 1
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else (1 if exc.code else 0)
    except Exception as e:
        print(f"Error executing command '{args.command}': {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
