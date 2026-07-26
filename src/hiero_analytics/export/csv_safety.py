"""Neutralise spreadsheet formulas in CSVs a human will open.

Cells beginning with ``= + - @`` (or a tab/CR) can execute as a formula when a
CSV is opened in Excel or Google Sheets — CSV injection. Much of what this
project publishes is attacker-controlled free text: anyone can open a PR in a
public repository and choose its title or branch name.

This applies only to copies meant for a spreadsheet — the browser download and
the API's companion files. The artifacts under ``outputs/data/`` are left
verbatim, because they are read by ``pandas.read_csv`` (which never evaluates
formulas) and prefixing them would corrupt the values for programmatic use.
"""

from __future__ import annotations

import csv
import io

# Mirrored in the frontend (web/src/safety.ts) so both download paths agree.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value: object) -> object:
    """Prefix a formula-triggering cell with ``'`` so it is treated as text.

    A lone ``-`` is left alone: it is a common empty-cell placeholder, not a
    formula.
    """
    text = str(value)
    if text and text != "-" and text[0] in FORMULA_PREFIXES:
        return "'" + text
    return value


def sanitize_csv_text(text: str) -> str:
    """Re-emit CSV text with every field neutralised against formulas.

    Parses rather than string-munges, so quoted fields containing commas or
    newlines survive intact.
    """
    rows = list(csv.reader(io.StringIO(text)))
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows([[csv_safe(cell) for cell in row] for row in rows])
    return buffer.getvalue()
