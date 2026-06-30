"""Safe environment-variable parsing with fallbacks and optional bounds.

Misconfigured numeric env vars (empty, non-numeric, zero/negative) should fall
back to a sane default rather than crash at import or feed an invalid value into
something like a thread-pool size. These helpers centralize that handling.
"""

from __future__ import annotations

import os


def env_int(name: str, default: int, *, minimum: int | None = None) -> int:
    """Read an int env var; fall back to ``default`` on missing/invalid input.

    When ``minimum`` is given the result is clamped to it, so misconfiguration
    can't produce a value that breaks downstream (e.g. a zero worker count).
    """
    try:
        value = int(os.getenv(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, value) if minimum is not None else value


def env_float(name: str, default: float, *, minimum: float | None = None) -> float:
    """Read a float env var; fall back to ``default`` on missing/invalid input."""
    try:
        value = float(os.getenv(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, value) if minimum is not None else value
