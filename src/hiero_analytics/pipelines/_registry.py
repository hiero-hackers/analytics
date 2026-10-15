"""The Pipeline record type behind the registry in the package ``__init__``."""

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
    # Org capabilities (config.orgs.CAPABILITIES) the pipeline needs. The full
    # run schedules a pipeline for every rendered org whose profile has all of
    # them, so the default (no requirement) means "runs for every org": a new
    # pipeline is multi-org unless it says otherwise.
    requires: frozenset[str] = frozenset()
    # Default-run pipelines execute in registry order during a full run (the
    # order CI used when they were separate steps); the others are CLI-only.
    in_default_run: bool = True

    @property
    def repo_scoped(self) -> bool:
        """Whether the pipeline analyses one repository (``GITHUB_REPO``) rather than an org.

        The full run executes these for the primary org only, since the
        configured repository belongs to it.
        """
        return "repo" in self.args

    def resolve(self) -> Callable[..., None]:
        """Import the pipeline module and return its ``main`` entry point."""
        return importlib.import_module(f"hiero_analytics.pipelines.{self.name}").main
