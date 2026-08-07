"""Neutralise spreadsheet formulas in CSVs a human will open.

Cells beginning with ``= + - @`` (or a control character) can execute as a
formula when a CSV is opened in Excel or Google Sheets — CSV injection. Much of
what this project publishes is attacker-controlled free text: anyone can open a
PR in a public repository and choose its title or branch name.

This applies only to copies meant for a spreadsheet — the browser download and
the API's companion files. The artifacts under ``outputs/data/`` are left
verbatim, because they are read by ``pandas.read_csv`` (which never evaluates
formulas) and prefixing them would corrupt the values for programmatic use.

Why the apostrophe and not OWASP's tab-inside-a-quoted-field: the tab survives
an Excel save-and-reopen cycle where the apostrophe may not, but it does so by
becoming part of the value, which every downstream reader of these files then
carries. These CSVs exist to be analysed, and the apostrophe already defuses
the first open — the attack this guards against. The residual path (a reader
re-saving the file in Excel and opening it again) is not worth paying for with
a tab in front of every value in every export.
"""

from __future__ import annotations

import csv
import io

# Mirrored in the frontend (web/src/safety.ts) so both download paths agree.
# The control characters are here because a leading tab, CR or LF is stripped
# on import, exposing whatever follows it to the formula parser.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


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
    # newline="" disables translation, so a bare CR stays inside the field
    # instead of tripping csv.reader.
    rows = list(csv.reader(io.StringIO(text, newline="")))
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows([[csv_safe(cell) for cell in row] for row in rows])
    return buffer.getvalue()
