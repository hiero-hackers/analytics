#!/usr/bin/env python3
"""Lint a drafted LFDT TAC report against the body rules in SKILL.md section 5.

Standard library only. The *body* is everything after the H1 and before the
first line starting with ``## Appendix``; the appendices are the rest and are
not linted (they are where identifiers, ``Source:`` lines and method remarks
belong).

Usage:
    check_draft.py DRAFT.md [--manifest PATH] [--max-numbers 6]

Hard failures (exit 1), each printed with its line number and the text:

- the first line is not the SPDX comment;
- a backtick-quoted token in the body, except inside a ``> [MAINTAINER INPUT]``
  blockquote (the whole contiguous quote block is exempt);
- a body line starting with ``Source:``;
- a body paragraph with more than ``--max-numbers`` numeric tokens (tables,
  quotes, headings, captions and the header are not paragraphs; link targets,
  ``[n]`` citations, "Figure N" references, hex-like revision tokens such as
  ``62a5652``, years and dates of every form are not counted);
- a ``[n]`` citation with no ``[n]`` entry in ``## Appendix: Sources``;
- a figure whose file is missing, or with no ``*Figure N.`` caption within
  three lines;
- with ``--manifest``: a dashboard link whose ``widget=`` is not a section,
  card or view id of the org in its ``org=`` parameter.

Warnings (printed, exit code unaffected): method-remark phrases, paragraphs
under two or over seven sentences, fewer than two or more than three
figures, more than three tables, a header longer than two lines, a header
without "Data as of".

Exit codes: 0 no hard failure, 1 at least one, 2 unreadable input.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, unquote

SPDX_LINE = "[//]: # (SPDX-License-Identifier: CC-BY-4.0)"
SLOT = "[MAINTAINER INPUT]"
DASHBOARD = "hiero-hackers.github.io/analytics/#"
FILED_REVIEW = {"words": 2500, "paragraphs": 30, "tables": 2}
METHOD_PHRASES = (
    "derived by this draft",
    "row_count",
    "the document's",
    "partial bucket",
    "not compared",
    "entity index",
    "population statement",
)
MIN_SENTENCES, MAX_SENTENCES = 2, 7
MIN_FIGURES, MAX_FIGURES = 2, 3
MAX_TABLES = 3
MAX_HEADER_LINES = 2
EXCERPT_WIDTH = 110

BACKTICK_RE = re.compile(r"`[^`\n]+`")
CITATION_RE = re.compile(r"\[(\d+)\](?!\()")
LINK_TARGET_RE = re.compile(r"\]\([^)]*\)")
MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
URL_RE = re.compile(r"https?://[^\s)>\]]+")
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
CAPTION_RE = re.compile(r"^\s*\*Figure\s+\d+\.")
SLOT_START_RE = re.compile(r"^\s*>\s*\[MAINTAINER INPUT\]")
SOURCE_LINE_RE = re.compile(r"^\s*Source:")
LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
SOURCES_ENTRY_RE = re.compile(r"^\s*(?:[-*]\s+)?\[(\d+)\]")
ABBREV_RE = re.compile(r"\b(?:e\.g|i\.e|vs|approx|cf)\.", re.IGNORECASE)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])[\"')\]*_]*\s+(?=[\"'(\[*_`A-Z0-9])")
FIGURE_REF_RE = re.compile(r"\bFigures?\s+\d+(?:(?:\s*[,\u2013-]\s*|\s+(?:to|and)\s+)\d+)*", re.IGNORECASE)
HEX_LIKE_RE = re.compile(r"\b(?=[0-9A-Za-z]*\d)(?=[0-9A-Za-z]*[A-Za-z])[0-9A-Za-z]{7,}\b")
MONTH = (
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December"
    r"|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\b"
)
YEAR = r"(?:19|20)\d{2}"
# Years and dates are context, not data; they are blanked out before counting.
ISO_DATE_RE = re.compile(
    r"(?<![\w.])\d{4}-(?:W\d{2}|\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?Z?)?|\d{2})(?!\d)"
)  # 2026-10-06, 2026-10-06T09:06Z, 2026-10, 2026-W41
HUMAN_DATE_RES = (
    # "6 to 9 October 2026": the leading day of a day range
    re.compile(rf"(?<![\w.])\d{{1,2}}\s*(?:to|[\u2013-])\s*(?=\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTH})"),
    # "6 October 2026" and "6 October"
    re.compile(rf"(?<![\w.])\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTH}(?:\s+{YEAR}(?![\w]|[.,]\d))?"),
    # "October 2026"
    re.compile(rf"\b{MONTH}\s+{YEAR}(?![\w]|[.,]\d)"),
    # "Q2 2025" and "2025 Q2"
    re.compile(rf"\bQ[1-4]\s+{YEAR}(?![\w]|[.,]\d)|(?<![\w.,]){YEAR}\s+Q[1-4]\b"),
)
YEAR_RE = re.compile(rf"(?<![\w.,]){YEAR}(?![\w]|[.,]\d)")  # a standalone year, 1900 to 2099
NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*%?")  # integer, decimal, thousands, percentage


@dataclass
class Finding:
    """One lint result; ``line`` is 1-based, or None when it concerns the whole file."""

    level: str  # "FAIL" or "WARN"
    line: int | None
    message: str
    text: str = ""


@dataclass
class Draft:
    """A parsed draft: raw lines, a kind per line, and where the body sits (0-based, end exclusive)."""

    lines: list[str]
    kinds: list[str]
    h1: int | None
    body_start: int
    body_end: int
    header_end: int

    def body(self) -> range:
        """Return the indices of the body lines."""
        return range(self.body_start, self.body_end)


@dataclass
class Block:
    """A run of prose lines (a paragraph) or one list item, as 0-based line indices."""

    kind: str  # "prose" or "list"
    lines: list[int] = field(default_factory=list)


@dataclass
class Stats:
    """Numbers shown in the summary block."""

    words: int = 0
    paragraphs: int = 0
    sentences: int = 0
    tables: int = 0
    figures: int = 0
    links: int = 0
    citations: set[int] = field(default_factory=set)
    sources: int | None = None
    slots: list[tuple[int, str, str]] = field(default_factory=list)
    goals_cells: int = 0


@dataclass
class Report:
    """Everything one lint run produced."""

    findings: list[Finding]
    stats: Stats

    def failures(self) -> list[Finding]:
        """Return the hard failures."""
        return [f for f in self.findings if f.level == "FAIL"]

    def warnings(self) -> list[Finding]:
        """Return the warnings."""
        return [f for f in self.findings if f.level == "WARN"]


# --- parsing -----------------------------------------------------------------


def classify_lines(lines: list[str]) -> list[str]:
    """Label every line: code, blank, heading, source, table, slot, quote, figure, caption, other, list, prose."""
    kinds: list[str] = []
    in_fence = False
    in_slot = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            kind = "code"
        elif in_fence:
            kind = "code"
        elif not stripped:
            kind = "blank"
        elif re.match(r"#{1,6}\s", stripped):
            kind = "heading"
        elif SOURCE_LINE_RE.match(line):
            kind = "source"
        elif stripped.startswith("|"):
            kind = "table"
        elif stripped.startswith(">"):
            in_slot = in_slot or bool(SLOT_START_RE.match(line))
            kind = "slot" if in_slot else "quote"
        elif stripped.startswith("!["):
            kind = "figure"
        elif CAPTION_RE.match(line):
            kind = "caption"
        elif stripped.startswith(("[//]:", "<!--")):
            kind = "other"
        elif LIST_RE.match(line):
            kind = "list"
        else:
            kind = "prose"
        if not stripped.startswith(">"):
            in_slot = False
        kinds.append(kind)
    return kinds


def parse_draft(text: str) -> Draft:
    """Split a draft into header, body and appendices."""
    lines = text.splitlines()
    kinds = classify_lines(lines)
    h1 = next((i for i, ln in enumerate(lines) if kinds[i] == "heading" and ln.startswith("# ")), None)
    body_start = h1 + 1 if h1 is not None else min(1, len(lines))
    body_end = next(
        (i for i in range(body_start, len(lines)) if kinds[i] == "heading" and lines[i].startswith("## Appendix")),
        len(lines),
    )
    header_end = next(
        (i for i in range(body_start, body_end) if kinds[i] == "heading" and lines[i].startswith("## ")),
        body_start,  # no section heading: there is no header region to exempt
    )
    return Draft(lines, kinds, h1, body_start, body_end, header_end)


def build_blocks(draft: Draft) -> list[Block]:
    """Group the body's prose lines into paragraphs; each list item is its own block."""
    blocks: list[Block] = []
    cur: Block | None = None
    for i in draft.body():
        kind = draft.kinds[i]
        if kind not in ("prose", "list"):
            cur = None
            continue
        indented = draft.lines[i][:1] in (" ", "\t")
        continues = cur is not None and kind == "prose" and (cur.kind == "prose" or indented)
        if continues and cur is not None:
            cur.lines.append(i)
        else:
            cur = Block(kind, [i])
            blocks.append(cur)
    return blocks


def block_text(draft: Draft, block: Block) -> str:
    """Join a block's lines into one string."""
    return " ".join(draft.lines[i].strip() for i in block.lines)


def sources_entries(draft: Draft) -> dict[int, int] | None:
    """Map citation number to 1-based line for the Sources appendix, or None when it is missing."""
    start = next(
        (
            i
            for i in range(draft.body_end, len(draft.lines))
            if draft.kinds[i] == "heading" and draft.lines[i].strip().lower().startswith("## appendix: sources")
        ),
        None,
    )
    if start is None:
        return None
    entries: dict[int, int] = {}
    for i in range(start + 1, len(draft.lines)):
        if draft.kinds[i] == "heading" and draft.lines[i].startswith("## "):
            break
        m = SOURCES_ENTRY_RE.match(draft.lines[i]) if draft.kinds[i] != "code" else None
        if m:
            entries.setdefault(int(m.group(1)), i + 1)
    return entries


# --- text helpers ------------------------------------------------------------


def excerpt(text: str, width: int = EXCERPT_WIDTH) -> str:
    """Collapse whitespace and truncate for display."""
    flat = " ".join(text.split())
    return flat if len(flat) <= width else flat[: width - 3] + "..."


def strip_refs(text: str) -> str:
    """Remove ``[n]`` citations, link targets and bare URLs so their digits are not counted."""
    text = CITATION_RE.sub("", text)
    text = LINK_TARGET_RE.sub("]", text)
    return URL_RE.sub(" ", text)


def count_numbers(text: str) -> int:
    """Count numeric tokens: integers, decimals and percentages; years and dates are context, not data.

    Not counted: link targets, URLs, ``[n]`` citations, "Figure N" references,
    hex-like tokens (7 or more letters and digits mixed, such as a git
    revision), standalone years 1900 to 2099, ISO dates, month buckets and weeks
    (2026-10-06, 2026-10, 2026-W41), and human dates ("6 October 2026",
    "6 October", "October 2026", "Q2 2025") including ranges of them. Everything
    else counts: ``3x``, ``180d`` and "26 of 44" (two).
    """
    text = HEX_LIKE_RE.sub(" ", FIGURE_REF_RE.sub(" ", strip_refs(text)))
    text = ISO_DATE_RE.sub(" ", text)
    for pattern in HUMAN_DATE_RES:
        text = pattern.sub(" ", text)
    return len(NUMBER_RE.findall(YEAR_RE.sub(" ", text)))


def count_sentences(text: str) -> int:
    """Count sentences in a paragraph (links reduced to their text, citations removed)."""
    text = CITATION_RE.sub("", text)
    text = URL_RE.sub(" ", MD_LINK_RE.sub(r"\1", text))
    text = ABBREV_RE.sub(lambda m: m.group(0).replace(".", "\x00"), text)
    return sum(1 for part in SENTENCE_SPLIT_RE.split(text.strip()) if re.search(r"\w", part))


def count_words(text: str) -> int:
    """Count words in a line, ignoring citations, link targets, URLs and table rules."""
    return sum(1 for tok in strip_refs(text).split() if re.search(r"\w", tok))


def urls_in(text: str) -> list[str]:
    """Return every URL in a line, markdown or bare, without trailing punctuation."""
    return [u.rstrip(".,;:") for u in URL_RE.findall(text)]


def nearest_heading(draft: Draft, index: int) -> str:
    """Return the closest heading line above ``index``."""
    for i in range(index - 1, -1, -1):
        if draft.kinds[i] == "heading":
            return draft.lines[i].strip()
    return "(no heading)"


# --- hard failures -----------------------------------------------------------


def check_spdx(draft: Draft) -> list[Finding]:
    """Fail unless the first line is exactly the SPDX comment."""
    first = draft.lines[0] if draft.lines else ""
    if first == SPDX_LINE:
        return []
    return [Finding("FAIL", 1, f"first line must be exactly {SPDX_LINE}", first)]


def check_backticks(draft: Draft) -> list[Finding]:
    """Fail on any backtick-quoted token in the body outside a maintainer-input slot."""
    out = []
    for i in draft.body():
        if draft.kinds[i] in ("code", "slot"):
            continue
        tokens = BACKTICK_RE.findall(draft.lines[i])
        if tokens:
            out.append(
                Finding("FAIL", i + 1, "backtick-quoted identifier in the body: " + " ".join(tokens), draft.lines[i])
            )
    return out


def check_source_lines(draft: Draft) -> list[Finding]:
    """Fail on any body line starting with ``Source:``."""
    return [
        Finding("FAIL", i + 1, "'Source:' line in the body (belongs under an appendix table)", draft.lines[i])
        for i in draft.body()
        if draft.kinds[i] == "source"
    ]


def check_numbers(draft: Draft, blocks: list[Block], max_numbers: int) -> list[Finding]:
    """Fail on any body paragraph with more numeric tokens than allowed (the header is exempt)."""
    out = []
    for block in blocks:
        if block.lines[0] < draft.header_end:
            continue
        text = block_text(draft, block)
        n = count_numbers(text)
        if n > max_numbers:
            out.append(
                Finding("FAIL", block.lines[0] + 1, f"paragraph has {n} numeric tokens (maximum {max_numbers})", text)
            )
    return out


def check_citations(draft: Draft) -> tuple[list[Finding], set[int], dict[int, int] | None]:
    """Fail on body citations with no Sources entry; also return the cited numbers and the entries."""
    entries = sources_entries(draft)
    cited: dict[int, list[int]] = {}
    for i in draft.body():
        if draft.kinds[i] == "code":
            continue
        for m in CITATION_RE.finditer(BACKTICK_RE.sub("", draft.lines[i])):
            cited.setdefault(int(m.group(1)), []).append(i)
    out: list[Finding] = []
    if cited and entries is None:
        first = min(v[0] for v in cited.values())
        out.append(
            Finding(
                "FAIL",
                first + 1,
                "citations used but there is no '## Appendix: Sources' section",
                draft.lines[first],
            )
        )
    elif entries is not None:
        for n, where in sorted(cited.items()):
            if n not in entries:
                more = f" ({len(where)} uses)" if len(where) > 1 else ""
                out.append(
                    Finding(
                        "FAIL",
                        where[0] + 1,
                        f"citation [{n}] has no entry in Appendix: Sources{more}",
                        draft.lines[where[0]],
                    )
                )
    return out, set(cited), entries


def check_figures(draft: Draft, draft_dir: Path) -> tuple[list[Finding], int]:
    """Fail on figures whose file is missing or that lack a ``*Figure N.`` caption; also count figures."""
    out = []
    count = 0
    for i in draft.body():
        if draft.kinds[i] != "figure":
            continue
        for m in IMAGE_RE.finditer(draft.lines[i]):
            count += 1
            target = unquote(m.group(2).split("#")[0].split("?")[0])
            if not re.match(r"[a-z][a-z0-9+.-]*://", target) and not (draft_dir / target).is_file():
                out.append(Finding("FAIL", i + 1, f"figure file not found beside the draft: {target}", draft.lines[i]))
            following = draft.lines[i + 1 : i + 4]
            if not any(CAPTION_RE.match(ln) for ln in following):
                out.append(
                    Finding("FAIL", i + 1, "figure has no '*Figure N.' italic caption within 3 lines", draft.lines[i])
                )
    return out, count


def manifest_ids(manifest: dict, org: str) -> set[str] | None:
    """Return the section, card and view ids for one org, or None when the org is not in the manifest."""
    data = manifest.get("orgs", {}).get(org)
    if data is None:
        return None
    ids: set[str] = set()
    for key in ("sections", "chart_sections", "views"):
        ids.update(item["id"] for item in data.get(key, []) if isinstance(item, dict) and "id" in item)
    return ids


def check_dashboard_links(draft: Draft, manifest: dict) -> list[Finding]:
    """Fail on dashboard deep links whose widget id is not in the manifest for the link's org."""
    out = []
    for i in draft.body():
        if draft.kinds[i] == "code":
            continue
        for url in urls_in(draft.lines[i]):
            if DASHBOARD not in url:
                continue
            params = parse_qs(url.split("#", 1)[1])
            widget = params.get("widget", [""])[0]
            if not widget:
                continue
            org = params.get("org", [""])[0]
            if not org:
                out.append(Finding("FAIL", i + 1, f"dashboard link has no org= parameter (widget={widget})", url))
                continue
            ids = manifest_ids(manifest, org)
            if ids is None:
                known = ", ".join(sorted(manifest.get("orgs", {})))
                out.append(Finding("FAIL", i + 1, f"org '{org}' is not in the manifest (known: {known})", url))
            elif widget not in ids:
                out.append(
                    Finding("FAIL", i + 1, f"widget '{widget}' is not a section, card or view id of org '{org}'", url)
                )
    return out


# --- warnings ----------------------------------------------------------------


def warn_phrases(draft: Draft) -> list[Finding]:
    """Warn on method-remark phrases in body text (maintainer-input slots are skipped)."""
    out = []
    for i in draft.body():
        if draft.kinds[i] in ("code", "slot"):
            continue
        low = draft.lines[i].lower().replace("’", "'")
        out.extend(
            Finding("WARN", i + 1, f"method-remark phrase '{phrase}' (belongs in an appendix)", draft.lines[i])
            for phrase in METHOD_PHRASES
            if phrase in low
        )
    return out


def warn_sentences(draft: Draft, blocks: list[Block]) -> tuple[list[Finding], int, int]:
    """Warn on paragraphs outside the 2 to 7 sentence range; return the warnings, paragraph and sentence counts."""
    out = []
    paragraphs = sentences = 0
    for block in blocks:
        if block.kind != "prose" or block.lines[0] < draft.header_end:
            continue
        text = block_text(draft, block)
        n = count_sentences(text)
        paragraphs += 1
        sentences += n
        if n < MIN_SENTENCES or n > MAX_SENTENCES:
            out.append(
                Finding(
                    "WARN",
                    block.lines[0] + 1,
                    f"paragraph has {n} sentence{'s' if n != 1 else ''} (aim for {MIN_SENTENCES} to {MAX_SENTENCES})",
                    text,
                )
            )
    return out, paragraphs, sentences


def count_tables(draft: Draft) -> int:
    """Count tables in the body: runs of consecutive table rows (quoted tables inside slots are not counted)."""
    tables = 0
    prev = ""
    for i in draft.body():
        if draft.kinds[i] == "table" and prev != "table":
            tables += 1
        prev = draft.kinds[i]
    return tables


def warn_shape(draft: Draft, figures: int, tables: int) -> list[Finding]:
    """Warn on figure and table counts and on a header that is long or lacks 'Data as of'."""
    out = []
    if not MIN_FIGURES <= figures <= MAX_FIGURES:
        out.append(Finding("WARN", None, f"{figures} figures in the body (aim for {MIN_FIGURES} to {MAX_FIGURES})"))
    if tables > MAX_TABLES:
        out.append(Finding("WARN", None, f"{tables} tables in the body (at most {MAX_TABLES})"))
    if draft.h1 is None:
        out.append(Finding("WARN", None, "no '# ' title found; the body is taken from line 2"))
    header = [i for i in range(draft.body_start, draft.header_end) if draft.lines[i].strip()]
    if len(header) > MAX_HEADER_LINES:
        out.append(
            Finding(
                "WARN",
                header[0] + 1,
                f"header runs to {len(header)} lines between the title and the first '## ' (it must be one line)",
                draft.lines[header[0]],
            )
        )
    if not any("Data as of" in draft.lines[i] for i in header):
        out.append(Finding("WARN", draft.body_start + 1, "header has no 'Data as of' statement"))
    return out


# --- driver ------------------------------------------------------------------


def collect_slots(draft: Draft) -> tuple[list[tuple[int, str, str]], int]:
    """Return the slots and the table-cell count.

    A slot is one contiguous ``> [MAINTAINER INPUT]`` blockquote block (listed
    with its first line and nearest heading), or a stray marker in plain prose.
    Markers inside table rows are goals-table cells, counted separately.
    """
    slots: list[tuple[int, str, str]] = []
    cells = 0
    prev = ""
    for i in draft.body():
        kind = draft.kinds[i]
        if kind == "slot" and prev != "slot":
            slots.append((i + 1, nearest_heading(draft, i), "blockquote"))
        elif kind == "table":
            cells += draft.lines[i].count(SLOT)
        elif kind in ("prose", "list") and SLOT in draft.lines[i]:
            slots.append((i + 1, nearest_heading(draft, i), "inline"))
        prev = kind
    return slots, cells


def lint(text: str, draft_dir: Path, max_numbers: int = 6, manifest: dict | None = None) -> Report:
    """Run every check over one draft and gather the findings and summary statistics."""
    draft = parse_draft(text)
    blocks = build_blocks(draft)
    stats = Stats()
    findings: list[Finding] = []

    findings += check_spdx(draft)
    findings += check_backticks(draft)
    findings += check_source_lines(draft)
    findings += check_numbers(draft, blocks, max_numbers)
    cite_findings, stats.citations, entries = check_citations(draft)
    findings += cite_findings
    fig_findings, stats.figures = check_figures(draft, draft_dir)
    findings += fig_findings
    if manifest is not None:
        findings += check_dashboard_links(draft, manifest)

    findings += warn_phrases(draft)
    sentence_warnings, stats.paragraphs, stats.sentences = warn_sentences(draft, blocks)
    findings += sentence_warnings
    stats.tables = count_tables(draft)
    findings += warn_shape(draft, stats.figures, stats.tables)

    body_lines = [i for i in draft.body() if draft.kinds[i] not in ("code", "figure", "blank")]
    stats.words = sum(count_words(draft.lines[i]) for i in body_lines)
    stats.links = sum(len(urls_in(draft.lines[i])) for i in body_lines)
    stats.sources = None if entries is None else len(entries)
    stats.slots, stats.goals_cells = collect_slots(draft)
    findings += warn_length(stats)
    return Report(findings, stats)


def warn_length(stats: Stats) -> list[Finding]:
    """Warn when the body is far shorter or longer than the filed review's shape."""
    out = []
    ref = FILED_REVIEW
    if stats.words < ref["words"] * 0.7:
        out.append(
            Finding(
                "WARN",
                None,
                f"body is {stats.words:,} words, under 70% of the filed review's {ref['words']:,}; "
                "the data sections are probably too thin, not the rules too strict",
            )
        )
    elif stats.words > ref["words"] * 1.3:
        out.append(
            Finding("WARN", None, f"body is {stats.words:,} words, over 130% of the filed review's {ref['words']:,}")
        )
    if stats.paragraphs < ref["paragraphs"] * 0.6:
        out.append(
            Finding(
                "WARN",
                None,
                f"{stats.paragraphs} body paragraphs against about {ref['paragraphs']} in the filed review; "
                "split long paragraphs and give each data section two or three",
            )
        )
    return out


def shape_line(stats: Stats) -> str:
    """Compare the draft with the filed-review shape in one line."""
    ref = FILED_REVIEW
    return (
        f"Filed-review shape (about {ref['words']:,} words, about {ref['paragraphs']} paragraphs, {ref['tables']} tables): "
        f"this draft has {stats.words:,} words ({stats.words - ref['words']:+,}), "
        f"{stats.paragraphs} paragraphs ({stats.paragraphs - ref['paragraphs']:+d}), "
        f"{stats.tables} tables ({stats.tables - ref['tables']:+d})."
    )


def format_findings(findings: list[Finding]) -> list[str]:
    """Render findings, ordered by line, each with an indented excerpt of the offending text."""
    out = []
    for f in sorted(findings, key=lambda f: (f.line is None, f.line or 0)):
        where = f"L{f.line}" if f.line else "file"
        out.append(f"{f.level}  {where:<6} {f.message}")
        if f.text:
            out.append(f"       | {excerpt(f.text)}")
    return out


def format_report(path: Path, report: Report) -> str:
    """Render the findings, the summary block and the result line."""
    s = report.stats
    out = [f"check_draft: {path}", ""]
    for title, items in (("Failures", report.failures()), ("Warnings", report.warnings())):
        out.append(f"{title} ({len(items)})")
        out += format_findings(items) or ["  none"]
        out.append("")
    out += [
        "Summary",
        f"  body words:               {s.words:,}",
        f"  paragraphs:               {s.paragraphs}",
        f"  sentences:                {s.sentences}",
        f"  tables:                   {s.tables}",
        f"  figures:                  {s.figures}",
        f"  body links:               {s.links}",
        f"  distinct [n] citations:   {len(s.citations)}",
        f"  Sources entries:          {'no Sources appendix' if s.sources is None else s.sources}",
        f"  {len(s.slots)} slot{'s' if len(s.slots) != 1 else ''} ({SLOT}):",
    ]
    out += [f"    L{line:<5} {heading} ({form})" for line, heading, form in s.slots]
    out.append(f"  goals-table cells:        {s.goals_cells}")
    out += ["  " + shape_line(s), ""]
    nf, nw = len(report.failures()), len(report.warnings())
    out.append(
        f"Result: {'FAIL' if nf else 'pass'} ({nf} failure{'s' if nf != 1 else ''}, {nw} warning{'s' if nw != 1 else ''})"
    )
    return "\n".join(out)


def main(argv: list[str]) -> int:
    """Parse arguments, lint the draft, print the report, and return the exit code."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("draft", help="the markdown draft to lint")
    ap.add_argument("--manifest", help="manifest.json: check dashboard widget ids against it")
    ap.add_argument("--max-numbers", type=int, default=6, help="numeric tokens allowed per body paragraph (default 6)")
    a = ap.parse_args(argv)
    path = Path(a.draft)
    try:
        text = path.read_text(encoding="utf-8")
        manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8")) if a.manifest else None
    except (OSError, ValueError) as exc:
        print(f"cannot read input: {exc}", file=sys.stderr)
        return 2
    report = lint(text, path.resolve().parent, a.max_numbers, manifest)
    print(format_report(path, report))
    return 1 if report.failures() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
