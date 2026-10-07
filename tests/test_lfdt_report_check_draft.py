"""Tests for the lfdt-report skill's draft linter (check_draft.py)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "lfdt-report" / "scripts"
SPDX = "[//]: # (SPDX-License-Identifier: CC-BY-4.0)"
DASH = "https://hiero-hackers.github.io/analytics/"
SOURCES = "## Appendix: Sources\n\n[1] Chart repo-growth, All time variant, data as of 2026-10-06.\n"
MANIFEST = {
    "orgs": {
        "hiero-ledger": {
            "sections": [{"id": "understaffed"}],
            "chart_sections": [{"id": "scorecard"}],
            "views": [{"id": "hip-board"}],
        },
        "other-org": {"sections": [{"id": "only-other"}], "chart_sections": [], "views": []},
    }
}


@pytest.fixture(scope="module")
def check():
    """Load check_draft.py from the skill directory (registered in sys.modules so its dataclasses resolve)."""
    spec = importlib.util.spec_from_file_location("check_draft", SCRIPTS / "check_draft.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["check_draft"] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop("check_draft", None)


def _draft(body: str, *, appendix: str = SOURCES, first: str = SPDX, header: str | None = None) -> str:
    """Wrap a body in the standard shell: SPDX line, H1, one-line header, one section, appendices."""
    header = "*Data as of 6 October 2026; period covered January to December 2026.*" if header is None else header
    return f"{first}\n\n# 2027 Annual Review Hiero\n\n{header}\n\n## Project Health\n\n{body}\n\n{appendix}"


def _lint(check, tmp_path: Path, text: str, **kw):
    """Lint ``text`` as if it were saved in ``tmp_path``."""
    return check.lint(text, tmp_path, **kw)


def _msgs(report, level: str) -> list[str]:
    """Return the messages of one level from a report."""
    return [f.message for f in report.findings if f.level == level]


def _has(report, level: str, fragment: str) -> bool:
    """Return True when any message of ``level`` contains ``fragment``."""
    return any(fragment in m for m in _msgs(report, level))


def _figures(tmp_path: Path, *names: str) -> None:
    """Create empty figure files under tmp_path/figures."""
    (tmp_path / "figures").mkdir(exist_ok=True)
    for name in names:
        (tmp_path / "figures" / name).write_text("<svg/>")


PARAGRAPH = "Hiero ended 2025 with 40 repositories [1]. Four were created this year. The count covers the organisation."


def test_passing_draft_exits_zero(check, tmp_path: Path, capsys):
    """A draft that follows every rule exits 0; its only warnings are the length-versus-filed-review ones."""
    _figures(tmp_path, "a.svg", "b.svg")
    body = (
        f"{PARAGRAPH}\n\n"
        "![Repositories per year](figures/a.svg)\n\n"
        "*Figure 1. Repositories at each year end.*\n\n"
        f"See the [dashboard card]({DASH}#tab=Governance&org=hiero-ledger&widget=scorecard). It shows the scores.\n\n"
        "![Maintainers by employer](figures/b.svg)\n\n"
        "*Figure 2. Maintainers by employer.*\n\n"
        "| Role | 2025 |\n|---|---|\n| Maintainers | 75 |\n\n"
        "> [MAINTAINER INPUT] What is being done about it.\n"
        "> Evidence in this draft: `repodiversity`, Figures 1 and 2.\n"
    )
    path = tmp_path / "draft.md"
    path.write_text(_draft(body, appendix=SOURCES + "\nSource: section `x`; `y`.\n"))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(MANIFEST))
    assert check.main([str(path), "--manifest", str(manifest)]) == 0
    out = capsys.readouterr().out
    assert "Result: pass (0 failures, " in out
    warnings = _msgs(_lint(check, tmp_path, path.read_text(), manifest=MANIFEST), "WARN")
    assert warnings and all("filed review" in m for m in warnings)  # a tiny draft is thin, nothing else is wrong
    assert "1 slot ([MAINTAINER INPUT]):" in out


@pytest.mark.parametrize("first", ["# Title", "", "[//]: # (SPDX-License-Identifier: MIT)", SPDX + " "])
def test_first_line_must_be_exact_spdx(check, tmp_path: Path, first: str):
    """Anything but the exact SPDX comment on line 1 is a hard failure at line 1."""
    report = _lint(check, tmp_path, _draft(PARAGRAPH, first=first))
    assert _has(report, "FAIL", "first line must be exactly")
    assert [f.line for f in report.failures()][0] == 1


def test_backticks_fail_in_body_but_not_in_slots_or_appendices(check, tmp_path: Path):
    """Identifiers in backticks fail in prose, tables and plain quotes; slots and appendices are exempt."""
    body = (
        "The `repodiversity` table lists them. A second sentence follows.\n\n"
        "| Col |\n|---|\n| `cell` |\n\n"
        "> a plain quote with `code`\n\n"
        "> [MAINTAINER INPUT] Question with `slot-id`.\n"
        "> Evidence in this draft: `repodiversity`.\n"
        ">\n"
        "> | `a` | `b` |\n"
    )
    report = _lint(check, tmp_path, _draft(body, appendix=SOURCES + "\nUse `BASE/x.json` here.\n"))
    flagged = [f for f in report.failures() if "backtick" in f.message]
    texts = " ".join(f.text for f in flagged)
    assert len(flagged) == 3
    assert "repodiversity` table" in texts and "`cell`" in texts and "a plain quote" in texts
    assert "slot-id" not in texts and "BASE/x.json" not in texts


def test_source_lines_fail_in_body_only(check, tmp_path: Path):
    """A body line starting with Source: fails; the same line in an appendix does not."""
    body = f"{PARAGRAPH}\nSource: section x; data as of 2026-10-06.\n"
    report = _lint(check, tmp_path, _draft(body, appendix=SOURCES + "\nSource: section y.\n"))
    hits = [f for f in report.failures() if "'Source:'" in f.message]
    assert len(hits) == 1
    assert "section x" in hits[0].text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # years and dates are context, not data
        ("on 2026-10-06 only", 0),
        ("in 2025 and 2026", 0),
        ("from 1900 to 2099", 0),
        ("buckets 2026-09 and 2026-10 and week 2026-W41", 0),
        ("on 6 October 2026 only", 0),
        ("on 6 October only", 0),
        ("since October 2026 or Oct 2026", 0),
        ("in Q2 2025 and 2025 Q3", 0),
        ("from 2024 to 2025, or 2018-2026", 0),
        ("from January to June 2026", 0),
        ("from 1 January to 30 June 2026", 0),
        ("on 6 to 9 October 2026", 0),
        ("on 1st March 2026", 0),
        ("6 October 2026 saw 44 repositories and 1,481 contributors", 2),
        ("26 of 44 repositories in 2026", 2),
        ("a count of 2100 and 1899 and 12.2026", 3),
        ("in 2025 there were 460 people, up from 330 in 2024", 2),
        ("77.5% of 1,481 people", 2),
        ("rose from 52 to 64", 2),
        ("see [3] and [12] for more", 0),
        ("see [the card](https://x.org/a/2026/10/06?n=5) for more", 0),
        ("a bare https://x.org/2026/10/06 link", 0),
        ("stamp 2026-10-06T09:06Z here", 0),
        ("see Figure 1 and Figure 2 for 5", 1),
        ("see Figures 1 to 3, then Figures 2 and 4 and Figures 1, 2, 3", 0),
        ("as in figure 4 above", 0),
        ("analytics revision 62a5652 and abcdef1", 0),
        ("a 1234567 still counts, as do 3x and 180d", 3),
        ("none at all", 0),
    ],
)
def test_count_numbers_rules(check, text: str, expected: int):
    """Quantities count; years, dates, ranges of them, URLs, [n] citations, Figure N and hex tokens do not."""
    assert check.count_numbers(text) == expected


def test_header_is_exempt_from_number_density(check, tmp_path: Path):
    """The header lines never fail the number check (they get the header warnings only); a body paragraph does."""
    dense = "Data as of 2026-10-06; counts were 11, 12, 13, 14, 15, 16 and 17 in 2026."
    report = _lint(check, tmp_path, _draft(PARAGRAPH, header=f"*{dense}*"))
    assert not _has(report, "FAIL", "numeric tokens")
    report = _lint(check, tmp_path, _draft(dense))
    assert _has(report, "FAIL", "numeric tokens")


def test_no_section_heading_means_no_header_exemption(check, tmp_path: Path):
    """Without any '## ' heading before the appendices there is no header region, so every paragraph is checked."""
    dense = "Counts were 1, 2, 3, 4, 5, 6 and 7 in 2026. A second sentence follows."
    text = f"{SPDX}\n\n# Title\n\n{dense}\n\n{SOURCES}"
    assert _has(_lint(check, tmp_path, text), "FAIL", "7 numeric tokens")


def test_paragraph_number_limit_and_override(check, tmp_path: Path):
    """More than --max-numbers numeric tokens fails; tables and quotes are not paragraphs."""
    six = "Counts were 1, 2, 3, 4, 5 and 6 on 2026-10-06 [1]. A second sentence has none."
    seven = "Counts were 1, 2, 3, 4, 5, 6 and 7 on 2026-10-06 [1]. A second sentence has none."
    table = "| a | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |\n|---|---|---|---|---|---|---|---|---|"
    quote = "> [MAINTAINER INPUT] 1 2 3 4 5 6 7 8 9.\n> Evidence in this draft: 10 11 12."
    assert not _has(_lint(check, tmp_path, _draft(f"{six}\n\n{table}\n\n{quote}")), "FAIL", "numeric tokens")
    report = _lint(check, tmp_path, _draft(seven))
    assert _has(report, "FAIL", "7 numeric tokens (maximum 6)")
    assert not _has(_lint(check, tmp_path, _draft(seven), max_numbers=7), "FAIL", "numeric tokens")
    assert _has(_lint(check, tmp_path, _draft(six), max_numbers=5), "FAIL", "6 numeric tokens (maximum 5)")


def test_citation_without_sources_entry_fails(check, tmp_path: Path):
    """A [n] with no matching entry in Appendix: Sources fails, naming the number."""
    body = "Hiero has 40 repositories [1]. It added four [2]. And more [2]."
    report = _lint(check, tmp_path, _draft(body))
    missing = [m for m in _msgs(report, "FAIL") if "no entry" in m]
    assert len(missing) == 1
    assert "[2]" in missing[0] and "2 uses" in missing[0]


def test_citations_with_no_sources_appendix_fail_once(check, tmp_path: Path):
    """When the Sources appendix is missing and citations exist, exactly one failure is raised."""
    body = "Hiero has 40 repositories [1]. It added four [2]."
    report = _lint(check, tmp_path, _draft(body, appendix="## Appendix: Data notes\n\nNothing.\n"))
    gone = [m for m in _msgs(report, "FAIL") if "no '## Appendix: Sources'" in m]
    assert len(gone) == 1
    assert report.stats.sources is None


def test_markdown_links_and_code_are_not_citations(check, tmp_path: Path):
    """Link text such as [2026](url) is not a citation, and neither is an index inside a backtick span."""
    body = f"The [2026]({DASH}) review is here. A second sentence follows."
    assert not _has(_lint(check, tmp_path, _draft(body)), "FAIL", "citation")


def test_figure_file_must_exist_and_have_caption(check, tmp_path: Path):
    """A figure needs its file beside the draft and an italic caption within three lines."""
    _figures(tmp_path, "ok.svg", "far.svg")
    body = (
        "![ok](figures/ok.svg)\n\n*Figure 1. Fine.*\n\n"
        "![gone](figures/gone.svg)\n\n*Figure 2. Missing file.*\n\n"
        "![nocap](figures/ok.svg)\n\nJust text, not a caption.\n\n"
        "![far](figures/far.svg)\n\nOne.\n\nTwo.\n\n*Figure 4. Too far.*\n"
    )
    report = _lint(check, tmp_path, _draft(body))
    fails = _msgs(report, "FAIL")
    assert sum("figure file not found" in m for m in fails) == 1
    assert sum("no '*Figure N.' italic caption" in m for m in fails) == 2
    assert report.stats.figures == 4
    assert any("gone.svg" in f.message for f in report.failures())


def test_dashboard_widget_ids_checked_against_manifest(check, tmp_path: Path):
    """With a manifest, widget ids must be a section, card or view id of the link's own org."""

    def link(widget: str, org: str | None = "hiero-ledger") -> str:
        org_part = f"&org={org}" if org else ""
        return f"[x]({DASH}#tab=Governance{org_part}&widget={widget})"

    good = "\n\n".join(link(w) + " ok." for w in ("understaffed", "scorecard", "hip-board"))
    assert not _has(_lint(check, tmp_path, _draft(good), manifest=MANIFEST), "FAIL", "widget")

    bad = _draft(
        "\n\n".join(
            [
                link("nope") + " unknown id.",
                link("only-other") + " id of a different org.",
                link("scorecard", "no-such-org") + " unknown org.",
                link("scorecard", None) + " no org.",
                f"[no widget]({DASH}#tab=Governance&org=hiero-ledger) fine.",
            ]
        )
    )
    report = _lint(check, tmp_path, bad, manifest=MANIFEST)
    fails = _msgs(report, "FAIL")
    assert any("widget 'nope' is not a section, card or view id of org 'hiero-ledger'" in m for m in fails)
    assert any("widget 'only-other' is not" in m for m in fails)
    assert any("org 'no-such-org' is not in the manifest" in m for m in fails)
    assert any("no org= parameter" in m for m in fails)
    assert len([m for m in fails if "widget" in m or "org" in m]) == 4
    assert not _has(_lint(check, tmp_path, bad), "FAIL", "widget")  # no manifest, no check


def test_method_remark_phrases_warn(check, tmp_path: Path):
    """Method-remark phrases in prose warn but do not fail; slots are skipped."""
    body = (
        "The row_count is derived by this draft from the entity index. Nothing else is said here.\n\n"
        "> [MAINTAINER INPUT] Anything.\n> Evidence in this draft: the document's population statement.\n"
    )
    report = _lint(check, tmp_path, _draft(body))
    phrases = [m for m in _msgs(report, "WARN") if "method-remark" in m]
    assert len(phrases) == 3
    assert not _has(report, "FAIL", "method-remark")
    for phrase in ("row_count", "derived by this draft", "entity index"):
        assert any(phrase in m for m in phrases)


@pytest.mark.parametrize(
    ("paragraph", "warns"),
    [
        ("Only one sentence here.", True),
        ("One is here. Two is here.", False),
        ("S1 is here. S2 is here. S3 is here. S4 is here. S5 is here. S6 is here. S7 is here.", False),
        ("S1 is here. S2 is here. S3 is here. S4 is here. S5 is here. S6 is here. S7 is here. S8 is here.", True),
        ("A value of 7.3 holds, e.g. in March. Another sentence follows.", False),
    ],
)
def test_paragraph_sentence_count_warns(check, tmp_path: Path, paragraph: str, warns: bool):
    """Paragraphs under two or over seven sentences warn; decimals and e.g. do not split sentences."""
    report = _lint(check, tmp_path, _draft(paragraph))
    assert _has(report, "WARN", "sentence") is warns


def test_figure_and_table_counts_warn(check, tmp_path: Path):
    """Fewer than two or more than three figures, and more than three tables, warn."""
    _figures(tmp_path, "a.svg")
    fig = "![a](figures/a.svg)\n\n*Figure 1. A.*"
    table = "| a |\n|---|\n| 1 |"
    none = _lint(check, tmp_path, _draft(PARAGRAPH))
    assert _has(none, "WARN", "0 figures in the body")
    assert not _has(none, "WARN", "tables in the body")

    many = _lint(check, tmp_path, _draft("\n\n".join([fig] * 4 + [table] * 4)))
    assert _has(many, "WARN", "4 figures in the body")
    assert _has(many, "WARN", "4 tables in the body")
    assert many.stats.tables == 4
    assert not many.failures()

    ok = _lint(check, tmp_path, _draft("\n\n".join([fig] * 2 + [table] * 3)))
    assert not _has(ok, "WARN", "figures in the body")
    assert not _has(ok, "WARN", "tables in the body")


def test_header_warnings(check, tmp_path: Path):
    """A header over two lines warns, and so does one without 'Data as of'."""
    long_header = "*Data as of 6 October 2026.*\n\nPeriod covered January to December 2026.\n\nAnother line."
    report = _lint(check, tmp_path, _draft(PARAGRAPH, header=long_header))
    assert _has(report, "WARN", "header runs to 3 lines")
    assert not _has(report, "WARN", "no 'Data as of'")

    wrapped = "*Data as of 6 October 2026 from the dashboard;\nperiod covered January to December 2026.*"
    assert not _has(_lint(check, tmp_path, _draft(PARAGRAPH, header=wrapped)), "WARN", "header")

    report = _lint(check, tmp_path, _draft(PARAGRAPH, header="*Period covered January to December 2026.*"))
    assert _has(report, "WARN", "header has no 'Data as of'")


def test_header_is_not_judged_as_a_paragraph(check, tmp_path: Path):
    """The one-sentence header never triggers the paragraph sentence-count warning."""
    assert not _has(_lint(check, tmp_path, _draft(PARAGRAPH)), "WARN", "sentence")


def test_appendices_are_not_linted(check, tmp_path: Path):
    """Backticks, Source: lines, number-heavy paragraphs and method phrases are fine after the first Appendix heading."""
    appendix = (
        SOURCES + "\n## Appendix: Supporting tables\n\n"
        "Source: section `understaffed`, `365d` period; row_count 4.\n\n"
        "Numbers 1 2 3 4 5 6 7 8 9 10 in the document's partial bucket.\n"
    )
    report = _lint(check, tmp_path, _draft(PARAGRAPH, appendix=appendix))
    assert not report.failures()
    assert not _has(report, "WARN", "method-remark")


def test_summary_counts_and_slots(check, tmp_path: Path, capsys):
    """The summary reports counts, each slot with its nearest heading, and the filed-review comparison."""
    _figures(tmp_path, "a.svg")
    body = (
        f"{PARAGRAPH}\n\n"
        f"A [link]({DASH}) and a [second]({DASH}#tab=Governance&org=hiero-ledger) are here. Cited again [1].\n\n"
        "![a](figures/a.svg)\n\n*Figure 1. A.*\n\n"
        "| a |\n|---|\n| 1 |\n\n"
        "### Community Calls\n\n"
        "> [MAINTAINER INPUT] Cadence.\n> Evidence in this draft: none.\n\n"
        "## Goals\n\n"
        "| Goal | Result |\n|---|---|\n| 1. X | [MAINTAINER INPUT] |\n"
    )
    path = tmp_path / "draft.md"
    path.write_text(_draft(body))
    assert check.main([str(path)]) == 0
    out = capsys.readouterr().out
    report = _lint(check, tmp_path, _draft(body))
    s = report.stats
    assert (s.paragraphs, s.sentences, s.tables, s.figures, s.links) == (2, 5, 2, 1, 2)
    assert s.citations == {1} and s.sources == 1
    assert [(line, heading) for line, heading, _ in s.slots] == [
        (path.read_text().splitlines().index("> [MAINTAINER INPUT] Cadence.") + 1, "### Community Calls"),
    ]
    assert s.goals_cells == 1
    assert "1 slot ([MAINTAINER INPUT]):" in out
    assert "### Community Calls (blockquote)" in out
    assert "goals-table cells:        1" in out
    assert "Filed-review shape (about 2,500 words, about 30 paragraphs, 2 tables)" in out


def test_slots_count_once_per_blockquote_block_and_cells_separately(check, tmp_path: Path):
    """A multi-line quote block is one slot; separate blocks are separate; table cells are counted apart."""
    body = (
        "### One\n\n"
        "> [MAINTAINER INPUT] First question.\n> Evidence in this draft: none.\n>\n> More lines.\n\n"
        "### Two\n\n"
        "> [MAINTAINER INPUT] Second question.\n\n"
        "> A plain quote, not a slot.\n\n"
        "### Goals\n\n"
        "| Goal | Result | Evidence |\n|---|---|---|\n"
        "| 1. A | [MAINTAINER INPUT] | none |\n| 2. B | [MAINTAINER INPUT] | none |\n"
    )
    stats = _lint(check, tmp_path, _draft(body)).stats
    assert [(heading, form) for _, heading, form in stats.slots] == [
        ("### One", "blockquote"),
        ("### Two", "blockquote"),
    ]
    assert stats.goals_cells == 2


def test_failures_print_line_number_and_text(check, tmp_path: Path, capsys):
    """Each failure prints its line number and the offending text, and the exit code is 1."""
    path = tmp_path / "draft.md"
    path.write_text(_draft("Uses `repodiversity` here. A second sentence follows."))
    assert check.main([str(path)]) == 1
    out = capsys.readouterr().out
    line = path.read_text().splitlines().index("Uses `repodiversity` here. A second sentence follows.") + 1
    assert f"FAIL  L{line}" in out
    assert "| Uses `repodiversity` here." in out
    assert "Result: FAIL (1 failure, " in out


def test_unreadable_input_exits_two(check, tmp_path: Path, capsys):
    """A missing draft or a malformed manifest exits 2 with a message on stderr."""
    assert check.main([str(tmp_path / "missing.md")]) == 2
    path = tmp_path / "draft.md"
    path.write_text(_draft(PARAGRAPH))
    bad = tmp_path / "manifest.json"
    bad.write_text("{not json")
    assert check.main([str(path), "--manifest", str(bad)]) == 2
    assert "cannot read input" in capsys.readouterr().err


def test_warn_length_flags_thin_and_sparse_bodies(check):
    """A body far under the filed review's words or paragraphs gets a shape warning, a matching one does not."""
    stats = check.Stats()
    stats.words, stats.paragraphs = 1300, 13
    messages = [f.message for f in check.warn_length(stats)]
    assert any("under 70%" in m for m in messages)
    assert any("body paragraphs" in m for m in messages)
    stats.words, stats.paragraphs = 2400, 28
    assert check.warn_length(stats) == []
    stats.words = 3400
    assert any("over 130%" in f.message for f in check.warn_length(stats))
