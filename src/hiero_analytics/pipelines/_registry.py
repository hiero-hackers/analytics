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
    # Default-run pipelines execute in registry order during a full run (the
    # order CI used when they were separate steps); the others are CLI-only.
    in_default_run: bool = True

    def resolve(self) -> Callable[..., None]:
        """Import the pipeline module and return its ``main`` entry point."""
        return importlib.import_module(f"hiero_analytics.pipelines.{self.name}").main
