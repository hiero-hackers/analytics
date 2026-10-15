"""The contributor-affiliation map: a generated file plus a hand-kept overrides file.

``data/affiliations.yaml`` is written by ``hiero-analytics build_affiliations``
from public signals and is never edited by hand. ``data/affiliation_overrides.yaml``
holds every hand correction, one ``login: "Organisation"  # reason`` row, and wins
over the generated value wherever both name a login. Keeping the two apart is
what makes a correction stable: there is no marker to forget on the generated
row, and a correction outlives the person's spell on the governance roster.

This module owns reading both files; ``analysis.affiliation`` consumes the merged
mapping as plain data.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

from hiero_analytics.config.paths import SRC

logger = logging.getLogger(__name__)

AFFILIATIONS_PATH = SRC / "data" / "affiliations.yaml"
OVERRIDES_PATH = SRC / "data" / "affiliation_overrides.yaml"
# Values that mean "no organisation". Shared with the generator so an override of
# "unknown" unsets a value there exactly as it does here.
UNKNOWN_VALUES = frozenset({"", "?", "unknown", "none"})
# The retired in-file convention: a row comment reading '# manual', '# manual: why',
# '# role # manual', '# role · manual' or the generator's old 'MANUAL — why'. Matched
# against the comment text only, and only as a marker, so a contributor whose display
# name is "Manual Rodriguez" is not mistaken for one.
LEGACY_MANUAL_MARKER_RE = re.compile(r"(?:^|#|·)\s*manual\b(?!\s+\w)|\bmanual\s*:|\bmanual\s+—", re.IGNORECASE)


def split_row(raw: str) -> tuple[str, str, str]:
    """Split a ``login: "Value"  # comment`` line into ``(login, value text, comment)``.

    The comment starts at the first ``#`` outside double quotes, so an organisation
    name containing ``#`` is not cut short. The comment is empty when absent.
    """
    login, _, rest = raw.partition(":")
    in_quotes = False
    for index, char in enumerate(rest):
        if char == '"' and (index == 0 or rest[index - 1] != "\\"):
            in_quotes = not in_quotes
        elif char == "#" and not in_quotes:
            return login.strip(), rest[:index].strip(), rest[index + 1 :].strip()
    return login.strip(), rest.strip(), ""


def _read_map(path) -> dict[str, str]:
    """One YAML file as ``lowercased login -> raw value``; empty when the file is missing."""
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(login).strip().lower(): str(org).strip() for login, org in raw.items()}


def load_overrides(path=OVERRIDES_PATH) -> dict[str, str]:
    """The hand corrections, ``lowercased login -> value``, unknown markers included.

    An override to ``"?"`` is meaningful: it *unsets* whatever the resolver guessed,
    so the raw value is kept here and only dropped by :func:`load_affiliations`.
    """
    return _read_map(path)


def load_override_rows(path=OVERRIDES_PATH) -> dict[str, tuple[str, str]]:
    """The hand corrections with their reasons: ``lowercased login -> (value, reason)``.

    The reason is the row's trailing comment. The generator logs it, and the
    override-file test insists on one, so every correction carries its evidence.
    """
    values = _read_map(path)
    if not values:
        return {}
    reasons: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.lstrip().startswith("#") or ":" not in raw:
            continue
        login, _value, comment = split_row(raw)
        reasons[login.lower()] = comment
    # Values come from the YAML parser, so they agree with load_overrides exactly.
    return {login: (value, reasons.get(login, "")) for login, value in values.items()}


def load_manual_logins(path=OVERRIDES_PATH) -> set[str]:
    """Lowercased logins that have a hand correction on file."""
    return set(_read_map(path))


def load_affiliations(path=AFFILIATIONS_PATH, overrides_path: Path | None = None) -> dict[str, str]:
    """The merged ``lowercased login -> organisation`` map the charts read.

    Overrides win over generated values. Unknown markers ('?', blank) are dropped
    after the merge, so a missing key, a generated '?', and an override that
    unsets a value are treated identically downstream.

    The overrides file lives beside the generated one, so ``overrides_path``
    defaults to ``affiliation_overrides.yaml`` in ``path``'s directory; a caller
    pointing at another generated file gets that file's own overrides, not the
    committed ones.
    """
    path = Path(path)
    if overrides_path is None:
        overrides_path = path.with_name(OVERRIDES_PATH.name)
    if not path.exists():
        logger.warning("Affiliations file not found: %s", path)
    merged = _read_map(path)
    merged.update(_read_map(overrides_path))
    return {login: value for login, value in merged.items() if value.lower() not in UNKNOWN_VALUES}
