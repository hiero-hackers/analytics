"""Cross-language contract: constants Python declares and the frontend restates.

A handful of values cannot travel through the data API, because the frontend
needs them before any fetch or wants them in CSS: the display formats a column
may declare, the characters a spreadsheet would read as a formula, and the HIP
coverage heat ramp. Each is written twice, once per language, and until now only
a source comment said the copies must agree.

A comment is not enforcement. Adding a ninth column format in Python leaves
``uv run pytest`` green, ``npm test`` green (its fixtures only cover what the
TypeScript union already allows) and the browser suite green — and the column
renders as unformatted text in production. Drifting ``FORMULA_PREFIXES`` is
worse: it silently unprotects one of the two CSV download paths against formula
injection. A drifted ramp is only cosmetic, but it splits the matrix cells from
the matplotlib charts that are meant to share a palette.

These tests read the frontend source and compare against Python, so drift fails
CI rather than shipping.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from hiero_analytics.config.charts import HIP_EVIDENCE_RAMP
from hiero_analytics.dashboard_spec import COLUMN_FORMATS
from hiero_analytics.export.csv_safety import FORMULA_PREFIXES

WEB_SRC = Path(__file__).resolve().parents[2] / "web" / "src"

# A TypeScript string literal in either quote style. Prettier rewrote web/ to
# single quotes, so a pattern that knew only double ones would match nothing.
# The mirrored declarations hold plain tokens and escapes like a tab, never an
# embedded quote of the same kind, so this needs no escape handling.
_STRING = re.compile("'[^']*'|\"[^\"]*\"")

COLUMN_FORMAT_UNION = re.compile(r"export type ColumnFormat\s*=(?P<body>[^;]*);")
FORMULA_PREFIX_ARRAY = re.compile(r"const FORMULA_PREFIXES\s*=\s*\[(?P<body>[^\]]*)\]")
# The ramp is spread over one custom property per bucket, not a single list, and
# it is declared twice: once in `:root` and again, deliberately inverted, in the
# dark-mode block. Only the light one has a Python counterpart, so the search is
# scoped to `:root` rather than taking whichever match comes first.
ROOT_BLOCK = re.compile(r"^:root\s*\{(?P<body>.*?)^\}", re.MULTILINE | re.DOTALL)
HEAT_CUSTOM_PROPERTY = re.compile(r"--heat-(?P<bucket>\d+):\s*(?P<colour>#[0-9a-fA-F]{3,8})\s*;")


def _literals(source: str, declaration: re.Pattern[str], what: str) -> set[str]:
    """The string literals of one TypeScript declaration, unescaped.

    Both failure modes are loud on purpose. A renamed or reformatted
    declaration would otherwise yield an empty set, and an empty set compared
    against an empty set is a test that passes while checking nothing.
    """
    match = declaration.search(source)
    assert match is not None, (
        f"could not find the {what} declaration in the TypeScript source. "
        f"If it was renamed or reformatted, update the pattern in {Path(__file__).name} — "
        f"do not delete this test, it is the only thing keeping the two languages in step."
    )
    found = _STRING.findall(match.group("body"))
    assert found, f"the {what} declaration parsed but held no string literals"
    # TypeScript and Python spell these literals the same way, escapes included,
    # so evaluating them as Python literals yields the exact characters the
    # Python side holds. `literal_eval` evaluates nothing but literals.
    return {ast.literal_eval(literal) for literal in found}


def test_column_format_union_matches_the_python_spec() -> None:
    """`ColumnFormat` in api.ts lists exactly `dashboard_spec.COLUMN_FORMATS`."""
    union = _literals((WEB_SRC / "api.ts").read_text(encoding="utf-8"), COLUMN_FORMAT_UNION, "ColumnFormat")

    assert union == set(COLUMN_FORMATS), (
        "web/src/api.ts ColumnFormat has drifted from dashboard_spec.COLUMN_FORMATS.\n"
        f"  only in Python: {sorted(set(COLUMN_FORMATS) - union)}\n"
        f"  only in TypeScript: {sorted(union - set(COLUMN_FORMATS))}\n"
        "A format Python emits but the union omits renders as unformatted text."
    )


def test_formula_prefixes_match_the_python_list() -> None:
    """`FORMULA_PREFIXES` in safety.ts matches `csv_safety.FORMULA_PREFIXES`.

    The two CSV download paths — the API's companion files, written in Python,
    and the browser's own export — must neutralise the same characters, or one
    of them ships a cell a spreadsheet will execute.
    """
    prefixes = _literals((WEB_SRC / "safety.ts").read_text(encoding="utf-8"), FORMULA_PREFIX_ARRAY, "FORMULA_PREFIXES")

    assert prefixes == set(FORMULA_PREFIXES), (
        "web/src/safety.ts FORMULA_PREFIXES has drifted from export/csv_safety.py.\n"
        f"  only in Python: {sorted(set(FORMULA_PREFIXES) - prefixes)!r}\n"
        f"  only in TypeScript: {sorted(prefixes - set(FORMULA_PREFIXES))!r}\n"
        "Whichever side is missing a character leaves that download path injectable."
    )


def test_heat_ramp_matches_the_python_palette() -> None:
    """`:root`'s `--heat-N` matches `config.charts.HIP_EVIDENCE_RAMP`, in order.

    Compared as a sequence, not a set: this is a ramp, so a palette holding the
    right colours in the wrong order is still wrong. The matrix cells read these
    CSS classes while the matplotlib charts read the Python tuple, and the two
    are meant to be one palette.

    The dark-mode block redefines the same properties on purpose — chart PNGs
    bake a light ground, so only the light ramp has a Python counterpart.
    """
    css = (WEB_SRC / "app.css").read_text(encoding="utf-8")
    root = ROOT_BLOCK.search(css)
    assert root is not None, (
        "could not find the `:root` block in web/src/app.css. If it was restructured, "
        f"update the pattern in {Path(__file__).name} rather than deleting this test."
    )
    buckets = HEAT_CUSTOM_PROPERTY.findall(root.group("body"))
    assert buckets, (
        "no --heat-N custom properties found in `:root`. If they were renamed, "
        f"update the pattern in {Path(__file__).name} rather than deleting this test."
    )
    ordered = sorted(buckets, key=lambda found: int(found[0]))

    # The identifiers matter as much as the colours. Sorting then discarding them
    # would let `--heat-1..4` plus `--heat-6` line up against a five-colour ramp
    # and pass, while the matrix's `.heat-5` cell points at a variable that does
    # not exist. Duplicates and an off-by-one start fail here for the same reason.
    identifiers = [int(bucket) for bucket, _ in ordered]
    expected_identifiers = list(range(1, len(HIP_EVIDENCE_RAMP) + 1))
    assert identifiers == expected_identifiers, (
        "web/src/app.css declares --heat-N buckets that do not line up with "
        "config.charts.HIP_EVIDENCE_RAMP.\n"
        f"  css buckets: {identifiers}\n"
        f"  expected:    {expected_identifiers}\n"
        "The matrix renders one class per bucket, so a gap or a renumbering leaves "
        "a cell pointing at a custom property nothing defines."
    )

    ramp = [colour.lower() for _, colour in ordered]
    assert ramp == [colour.lower() for colour in HIP_EVIDENCE_RAMP], (
        "web/src/app.css --heat-N has drifted from config.charts.HIP_EVIDENCE_RAMP.\n"
        f"  css:    {ramp}\n"
        f"  python: {[colour.lower() for colour in HIP_EVIDENCE_RAMP]}\n"
        "The coverage matrix and the charts would then render different palettes."
    )


def test_a_renamed_declaration_fails_instead_of_matching_nothing() -> None:
    """The guard above is load-bearing: prove it fires rather than passing empty."""
    for source, expected in (
        ('export type Something = "a";', "could not find"),
        ("export type ColumnFormat = ;", "no string literals"),
    ):
        try:
            _literals(source, COLUMN_FORMAT_UNION, "ColumnFormat")
        except AssertionError as error:
            assert expected in str(error)
        else:  # pragma: no cover - only reached if the guard regresses
            raise AssertionError(f"expected an AssertionError containing {expected!r}")
