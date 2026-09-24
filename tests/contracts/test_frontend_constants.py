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

import pytest

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
# it is declared twice: unconditionally in `:root`, and again, deliberately
# inverted, inside the dark-mode `@media`. Only the light one has a Python
# counterpart, so the scan below keeps `:root` rules that no `@media` wraps.
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
# Conditional wrappers. `@layer` is deliberately absent: it only orders the
# cascade, so a `:root` inside one still applies unconditionally.
_CONDITIONAL_AT_RULES = ("@media", "@supports", "@container")
HEAT_CUSTOM_PROPERTY = re.compile(r"--heat-(?P<bucket>\d+):\s*(?P<colour>#[0-9a-fA-F]{3,8})\s*;")


def _unconditional_root_bodies(css: str) -> list[str]:
    """The body of every `:root` rule that applies whatever the viewer's settings.

    Found by matching braces rather than by where a line starts. Column 0 stood
    in for "not inside an `@media`", so wrapping `:root` in an `@layer`, or adding
    a second top-level `:root` for `color-scheme`, would have broken the check
    without the ramp having moved. Comments are dropped first, since one may
    mention braces; `;` ends an at-rule statement such as `@layer a, b;`, which
    would otherwise be read as the start of the next rule's selector.
    """
    css = _CSS_COMMENT.sub("", css)
    bodies: list[str] = []
    preludes: list[str] = []  # selector or at-rule text of each enclosing block
    body_starts: list[int] = []
    prelude_from = 0
    for index, char in enumerate(css):
        if char == "{":
            preludes.append(css[prelude_from:index].strip())
            body_starts.append(index + 1)
            prelude_from = index + 1
        elif char == "}":
            if preludes:
                selector = preludes.pop()
                start = body_starts.pop()
                if selector == ":root" and not any(p.startswith(_CONDITIONAL_AT_RULES) for p in preludes):
                    bodies.append(css[start:index])
            prelude_from = index + 1
        elif char == ";":
            prelude_from = index + 1
    return bodies


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
    bake a light ground, so only the light ramp has a Python counterpart. It is
    told apart by its `@media` wrapper, not by where it sits in the file.
    """
    css = (WEB_SRC / "app.css").read_text(encoding="utf-8")
    bodies = _unconditional_root_bodies(css)
    assert bodies, (
        "could not find an unconditional `:root` rule in web/src/app.css. If the "
        f"stylesheet was restructured, update the scan in {Path(__file__).name} "
        "rather than deleting this test."
    )
    buckets = HEAT_CUSTOM_PROPERTY.findall("\n".join(bodies))
    assert buckets, (
        "no --heat-N custom properties found in an unconditional `:root`. If they were "
        f"renamed, update the pattern in {Path(__file__).name} rather than deleting this test."
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


ROOT_SCAN_CASES = {
    "top level": (":root { --a: 1; }", ["--a: 1;"]),
    "indented with tabs": ("\t:root {\n\t\t--a: 1;\n\t}", ["--a: 1;"]),
    "inside @layer still applies": ("@layer theme { :root { --a: 1; } }", ["--a: 1;"]),
    "after an at-rule statement": ("@layer theme, base;\n:root { --a: 1; }", ["--a: 1;"]),
    "after @import": ('@import "x.css";\n:root { --a: 1; }', ["--a: 1;"]),
    "two top-level blocks are both read": (":root { --a: 1; }\n:root { --b: 2; }", ["--a: 1;", "--b: 2;"]),
    "inside dark @media is skipped": ("@media (prefers-color-scheme: dark) { :root { --a: 1; } }", []),
    "inside any @media is skipped": ("@media (max-width: 600px) { :root { --a: 1; } }", []),
    "inside @layer inside @media is skipped": ("@media print { @layer x { :root { --a: 1; } } }", []),
    "unconditional kept beside a skipped dark one": (
        ":root { --a: 1; }\n@media (prefers-color-scheme: dark) { :root { --a: 2; } }",
        ["--a: 1;"],
    ),
    "a comment mentioning braces is ignored": ("/* :root { --a: 9; } */\n:root { --a: 1; }", ["--a: 1;"]),
    "a different selector is not :root": (':root[data-theme="dark"] { --a: 1; }\n.x { --a: 2; }', []),
    "nothing to find": (".card { --a: 1; }", []),
}


@pytest.mark.parametrize(("css", "expected"), ROOT_SCAN_CASES.values(), ids=ROOT_SCAN_CASES.keys())
def test_root_scan_finds_only_unconditional_root_rules(css: str, expected: list[str]) -> None:
    """The scan reads `:root` by structure, so layout and nesting cannot fool it."""
    assert [body.strip() for body in _unconditional_root_bodies(css)] == expected


def test_root_scan_survives_unbalanced_braces() -> None:
    """A stray closing brace must not crash the scan or invent a `:root` rule."""
    assert _unconditional_root_bodies("} } :root { --a: 1; }") == [" --a: 1; "]


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
