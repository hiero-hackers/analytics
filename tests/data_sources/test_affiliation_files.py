"""Offline guards over the committed affiliation data files.

``affiliations.yaml`` is machine-written and ``affiliation_overrides.yaml`` is
hand-kept. Nothing at run time would notice a hand edit that breaks the split
between them: a marker pasted back into the generated file is silently lost on
the next regeneration, and a duplicate override key is silently collapsed by the
YAML parser. These tests read the real files and fail on a bad edit.
"""

from __future__ import annotations

from collections import Counter

import pytest
import yaml

from hiero_analytics.data_sources.affiliations import AFFILIATIONS_PATH, LEGACY_MANUAL_MARKER_RE, OVERRIDES_PATH

_MANUAL = LEGACY_MANUAL_MARKER_RE  # the same pattern the generator's guard applies


def _split_row(raw: str) -> tuple[str, str, str]:
    """Split ``login: "Value"  # comment`` into ``(login, value text, comment)``.

    The comment starts at the first ``#`` outside double quotes, so an organisation
    name containing ``#`` is not mistaken for one. The comment is empty when absent.
    """
    login, _, rest = raw.partition(":")
    in_quotes = False
    for i, char in enumerate(rest):
        if char == '"' and (i == 0 or rest[i - 1] != "\\"):
            in_quotes = not in_quotes
        elif char == "#" and not in_quotes:
            return login.strip(), rest[:i].strip(), rest[i + 1 :].strip()
    return login.strip(), rest.strip(), ""


def _rows(path) -> list[tuple[str, str, str]]:
    """Every ``login: value  # comment`` row of a YAML file, as ``(login, value text, comment)``.

    Blank lines and ``#`` comment lines (the header) are not rows. The file must
    have rows, so a broken reader cannot make every guard below pass vacuously.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    rows = [_split_row(raw) for raw in lines if raw.strip() and not raw.lstrip().startswith("#")]
    assert rows, f"{path.name} has no rows"
    return rows


@pytest.fixture(scope="module")
def override_rows() -> list[tuple[str, str, str]]:
    """The committed overrides file's rows."""
    return _rows(OVERRIDES_PATH)


# -- the generated file ---------------------------------------------------------


def test_generated_file_is_labelled_generated():
    """The first line says the file is machine-written, so nobody mistakes it for a place to hand-correct."""
    first_line = AFFILIATIONS_PATH.read_text(encoding="utf-8").splitlines()[0]

    assert first_line.startswith("# GENERATED")


def test_generated_file_has_no_manual_markers():
    """No generated row carries a 'manual' comment: hand corrections belong in the overrides file."""
    marked = [login for login, _value, comment in _rows(AFFILIATIONS_PATH) if _MANUAL.search(comment)]

    assert not marked, f"move these to {OVERRIDES_PATH.name}, regeneration would overwrite them: {marked}"


# -- the overrides file ---------------------------------------------------------


def test_overrides_file_parses_to_a_flat_str_to_str_dict():
    """The overrides file is one flat mapping of string login to string organisation."""
    parsed = yaml.safe_load(OVERRIDES_PATH.read_text(encoding="utf-8"))

    assert isinstance(parsed, dict)
    assert parsed, "overrides file parses to an empty mapping"
    for login, value in parsed.items():
        # A bare `no:` or `on:` login would parse as a bool, a bare `~` value as None.
        assert isinstance(login, str), f"login {login!r} is not a string (quote it)"
        assert isinstance(value, str), f"{login}: value {value!r} is not a string (quote it)"


def test_override_logins_are_lowercase_and_stripped():
    """Logins are stored lowercased and without stray whitespace, the form the loader compares against."""
    parsed = yaml.safe_load(OVERRIDES_PATH.read_text(encoding="utf-8"))

    bad = [login for login in parsed if login != login.strip().lower()]
    assert not bad, f"logins must be lowercase with no surrounding whitespace: {bad}"


def test_override_logins_are_unique(override_rows):
    """No login appears on two rows: the YAML parser would silently keep only the last."""
    counts = Counter(login.strip("\"'").lower() for login, _value, _comment in override_rows)

    duplicates = sorted(login for login, count in counts.items() if count > 1)
    assert not duplicates, f"logins on more than one row: {duplicates}"


def test_every_override_row_gives_a_reason(override_rows):
    """Each row ends in a non-empty '# reason' comment saying what the evidence was."""
    missing = [login for login, _value, comment in override_rows if not comment]

    assert not missing, f"override rows with no reason after '#': {missing}"


def test_every_override_value_is_a_non_empty_string():
    """Each value names an organisation, 'Independent', or '?'; blank would be indistinguishable from unset."""
    parsed = yaml.safe_load(OVERRIDES_PATH.read_text(encoding="utf-8"))

    empty = [login for login, value in parsed.items() if not isinstance(value, str) or not value.strip()]
    assert not empty, f"override rows with an empty value: {empty}"
