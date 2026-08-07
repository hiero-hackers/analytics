"""Formula neutralisation for CSVs a human will open in a spreadsheet."""

from __future__ import annotations

import pytest

from hiero_analytics.export.csv_safety import csv_safe, sanitize_csv_text


@pytest.mark.parametrize("value", ["=1+1", "+1", "-1+1", "@SUM(A1)", "\tcmd", "\rcmd", "\ncmd"])
def test_formula_triggers_are_prefixed(value):
    """Every prefix a spreadsheet would evaluate is defused."""
    assert csv_safe(value) == f"'{value}"


def test_ordinary_values_and_the_placeholder_are_untouched():
    """Normal text must survive verbatim, including the lone-hyphen placeholder."""
    assert csv_safe("feat: add HIP-1200 support") == "feat: add HIP-1200 support"
    assert csv_safe("-") == "-"  # empty-cell placeholder, not a formula
    assert csv_safe(42) == 42


def test_sanitize_preserves_quoted_fields_while_defusing_them():
    """A PR title is attacker-chosen text that may contain commas and quotes."""
    text = 'repo,title\nhiero,"=HYPERLINK(""https://evil.test"",""click""), now"\n'

    cleaned = sanitize_csv_text(text)

    assert cleaned.splitlines()[1] == 'hiero,"\'=HYPERLINK(""https://evil.test"",""click""), now"'
    # Round-trips as one row of two fields, i.e. the structure survived.
    import csv
    import io

    rows = list(csv.reader(io.StringIO(cleaned)))
    assert len(rows) == 2 and len(rows[1]) == 2


def test_sanitize_leaves_a_clean_file_semantically_identical():
    """A file with nothing to defuse round-trips unchanged."""
    text = "stage,share\nproposed,100\napproved,88\n"

    assert sanitize_csv_text(text) == text


def test_sanitize_handles_a_bare_carriage_return_in_a_field():
    """A stray CR must not abort the export with a csv.Error."""
    text = "name,formula\rvalue"

    assert sanitize_csv_text(text) == "name,formula\nvalue\n"
