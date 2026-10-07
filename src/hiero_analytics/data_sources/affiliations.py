"""The curated contributor-affiliation map (``data/affiliations.yaml``).

A hand-maintained login -> organisation mapping, regenerated from public
signals by the ``build_affiliations`` pipeline and corrected by hand where
those signals are wrong (rows whose comment says ``manual``). This module owns
reading it; ``analysis.affiliation`` consumes the mapping as plain data.
"""

from __future__ import annotations

import logging
import re

import yaml

from hiero_analytics.config.paths import SRC

logger = logging.getLogger(__name__)

AFFILIATIONS_PATH = SRC / "data" / "affiliations.yaml"
_UNKNOWN_VALUES = {"", "?", "unknown", "none"}


def load_affiliations(path=AFFILIATIONS_PATH) -> dict[str, str]:
    """Load the curated login -> organisation map, keyed by lowercased login.

    Unknown markers ('?', blank) are dropped, so a missing key and an explicit
    '?' are treated identically downstream.
    """
    if not path.exists():
        logger.warning("Affiliations file not found: %s", path)
        return {}

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    mapping: dict[str, str] = {}
    for login, org in raw.items():
        value = str(org).strip()
        if value.lower() in _UNKNOWN_VALUES:
            continue
        mapping[str(login).strip().lower()] = value
    return mapping


def load_manual_logins(path=AFFILIATIONS_PATH) -> set[str]:
    """Lowercased logins whose value was hand-set (YAML comment marked manual/MANUAL)."""
    if not path.exists():
        return set()
    manual: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.lstrip().startswith("#") or ":" not in raw:
            continue
        body, sep, comment = raw.partition("#")
        if not sep:
            continue
        # 'manual' anywhere in the comment — at the start, appended after the role
        # tag ('# maintainer # manual'), or the generator's '… · MANUAL — …'.
        if re.search(r"\bmanual\b", comment, re.IGNORECASE):
            manual.add(body.split(":", 1)[0].strip().lower())
    return manual
