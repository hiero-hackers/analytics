"""Logging configuration helpers for ``hiero_analytics``."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable

DEFAULT_LOG_LEVEL = logging.INFO
LOG_LEVEL_ENV_VAR = "LOG_LEVEL"
LOG_MODULES_ENV_VAR = "LOG_MODULES"
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


class _ModuleFilter(logging.Filter):
    """Limit low-severity output to selected module prefixes."""

    def __init__(self, modules: tuple[str, ...]) -> None:
        super().__init__()
        self._modules = modules

    def filter(self, record: logging.LogRecord) -> bool:
        """Allow warnings globally and limit info/debug to selected modules."""
        if record.levelno >= logging.WARNING:
            return True

        if record.name == __name__:
            return True

        return any(
            record.name == module or record.name.startswith(f"{module}.")
            for module in self._modules
        )


def _normalize_modules(modules: Iterable[str] | str | None) -> tuple[str, ...]:
    """Normalize module names from code or environment-variable input."""
    if modules is None:
        return ()

    candidates = modules.split(",") if isinstance(modules, str) else modules

    normalized: list[str] = []
    seen: set[str] = set()

    for module in candidates:
        module_name = module.strip()
        if not module_name or module_name in seen:
            continue
        normalized.append(module_name)
        seen.add(module_name)

    return tuple(normalized)


def _resolve_log_level(level: str | int | None) -> tuple[int, str | int | None]:
    """Resolve a logging level, returning an invalid value when fallback is used."""
    if level is None:
        return DEFAULT_LOG_LEVEL, None

    if isinstance(level, int):
        return level, None

    normalized = level.strip().upper()
    if not normalized:
        return DEFAULT_LOG_LEVEL, None

    if normalized.isdecimal():
        return int(normalized), None

    resolved_level = logging.getLevelNamesMapping().get(normalized)
    if isinstance(resolved_level, int):
        return resolved_level, None

    return DEFAULT_LOG_LEVEL, level


def setup_logging(
    level: str | int | None = None,
    *,
    modules: Iterable[str] | str | None = None,
) -> None:
    """Configure application logging with optional module-focused filtering."""
    requested_level = (
        level
        if level is not None
        else os.getenv(LOG_LEVEL_ENV_VAR, logging.getLevelName(DEFAULT_LOG_LEVEL))
    )
    requested_modules = (
        modules
        if modules is not None
        else os.getenv(LOG_MODULES_ENV_VAR)
    )

    resolved_level, invalid_level = _resolve_log_level(requested_level)
    normalized_modules = _normalize_modules(requested_modules)

    logging.basicConfig(
        level=resolved_level,
        format=LOG_FORMAT,
        force=True,
    )

    root_logger = logging.getLogger()
    if normalized_modules:
        module_filter = _ModuleFilter(normalized_modules)
        for handler in root_logger.handlers:
            handler.addFilter(module_filter)

    logger = logging.getLogger(__name__)

    if invalid_level is not None:
        logger.warning(
            "Unknown log level %r. Falling back to %s.",
            invalid_level,
            logging.getLevelName(DEFAULT_LOG_LEVEL),
        )

    if normalized_modules:
        logger.info(
            "Logging configured at %s for modules: %s",
            logging.getLevelName(resolved_level),
            ", ".join(normalized_modules),
        )
        return

    logger.info(
        "Logging configured at %s for all modules",
        logging.getLevelName(resolved_level),
    )


if __name__ == "__main__":
    # Example usage and demonstration of filtering
    import sys

    # 1. Default configuration (INFO level, all modules)
    setup_logging()
    logging.getLogger("some.module").info("Default: This should be visible")
    logging.getLogger("some.module").debug("Default: This should NOT be visible")

    # 2. Focused logging (DEBUG level, but only for specific modules)
    # This allows deep debugging of one area without being drowned in noise from others.
    setup_logging(level="DEBUG", modules="hiero_analytics.data_sources")

    # Visible because it matches the module prefix and level
    logging.getLogger("hiero_analytics.data_sources.client").debug(
        "Focus: Visible DEBUG from filtered module"
    )
    # Visible because WARNING and above are always shown globally
    logging.getLogger("other.library").warning(
        "Focus: Visible WARNING from any module"
    )
    # NOT visible because it doesn't match the module prefix and is below WARNING
    logging.getLogger("other.library").info(
        "Focus: Hidden INFO from non-filtered module"
    )

    # 3. Environment variable control
    # You can also control this via LOG_LEVEL and LOG_MODULES env vars
    os.environ[LOG_LEVEL_ENV_VAR] = "DEBUG"
    os.environ[LOG_MODULES_ENV_VAR] = "myapp.core,myapp.api"
    setup_logging()  # Uses env vars when arguments are omitted
    logging.getLogger("myapp.core").debug("Env: Visible DEBUG from myapp.core")
    logging.getLogger("myapp.other").debug("Env: Hidden DEBUG from myapp.other")
