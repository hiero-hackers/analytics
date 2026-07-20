"""CLI entrypoint for hiero-analytics."""
from __future__ import annotations

import argparse

from dataclasses import dataclass
import sys
from typing import Callable, Sequence

@dataclass
class Command:
    name: str | None = None
    description: str | None = None
    func: Callable | None = None


commands: list[Command] = [
    Command(
        name="all", 
        description="Run the full suite of analytics pipelines",
        func=lambda args: __import__("hiero_analytics.run_all", fromlist=["main"]).main()
    ),

    Command(
        name="scorecard",
        description="Generate scorecard metrics for an organization",
        func=lambda args: __import__("hiero_analytics.run_scorecard_for_org", fromlist=["main"]).main()
    ),

    Command(
        name="dashboard",
        description="Generate the org analytics dashboard",
        func=lambda args: __import__("hiero_analytics.run_dashboard", fromlist=["main"]).main()
    ),

    Command(
        name="onboarding",
        description="Analyze repo onboarding signals",
        func=lambda args: __import__("hiero_analytics.run_onboarding", fromlist=["main"]).main()
    ),

    Command(
        name="maintainer",
        description="Run maintainer analytics pipeline",
        func=lambda args: __import__("hiero_analytics.run_maintainer_pipeline_org", fromlist=["main"]).main()    
    ),

    Command(
        name="roles",
        description="Analyze role coverage for organization",
        func=lambda args: __import__("hiero_analytics.run_role_coverage_org", fromlist=["main"]).main()
    ),

    Command(
        name="affiliation",
        description="Map contributor affiliations",
        func=lambda args: __import__("hiero_analytics.run_affiliation_org", fromlist=["main"]).main()
    ),

    Command(
        name="codeowners",
        description="Analyze CODEOWNERS and workflow runners",
        func=lambda args: __import__("hiero_analytics.run_codeowner_and_runner", fromlist=["main"]).main()
    ),

    Command(
        name="activity",
        description="Run contributor activity analysis",
        func=lambda args: __import__("hiero_analytics.run_contributor_activity_org", fromlist=["main"]).main()
    ),

    Command(
        name="heatmap",
        description="Generate contributor activity heatmaps",
        func=lambda args: __import__("hiero_analytics.run_contributor_heatmap_org", fromlist=["main"]).main()
    ),

    Command(
        name="profiles",
        description="Analyze contributor profiles",
        func=lambda args: __import__("hiero_analytics.run_contributor_profiles_repo", fromlist=["main"]).main()
    ),

    Command(
        name="difficulty",
        description="Run repo difficulty analysis",
        func=lambda args: __import__("hiero_analytics.run_difficulty_org_for_repo", fromlist=["main"]).main()
    ),

    Command(
        name="difficulty-time",
        description="Run difficulty over time analysis",
        func=lambda args: __import__("hiero_analytics.run_difficulty_over_time_org", fromlist=["main"]).main()
    ),

    Command(
        name="discord",
        description="Run discord analysis",
        func=lambda args: __import__("hiero_analytics.run_hiero_discord_analytics", fromlist=["main"]).main()
    ),

    Command(
        name="hackers",
        description="Run Hiero Hackers org analytics",
        func=lambda _: __import__("hiero_analytics.run_hiero_hackers_org", fromlist=["main"]).main()
    ),

    Command(
        name="churn",
        description="Analyze contributor churn",
        func=lambda _: __import__("hiero_analytics.run_contributor_churn_analysis", fromlist=["main"]).main()
    )
]

def _build_parser() -> argparse.ArgumentParser:
    """Build the ArgumnetParser for the Commands."""
    parser = argparse.ArgumentParser(prog="hiero-analytics", description="CLI for Hiero repository analytics and reporting")
    
    subparsers = parser.add_subparsers(
        dest="command",
        title="available commands",
        description="Run `hiero-analytics <command> --help` for specific subcommand options.",
        metavar="<command>",
    )

    for command in commands:
        command_parser = subparsers.add_parser(command.name, help=command.description)
        command_parser.set_defaults(func=command.func)

    return parser


def main(argv: Sequence[str] | None = None):
    """Entry point for the CLI"""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1
    
    try:
        args.func(args)
        return 1
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else (1 if exc.code else 0)
    except Exception as e:
        print(f"Error executing command '{args.command}': {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())