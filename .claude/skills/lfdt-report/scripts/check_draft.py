#!/usr/bin/env python3
"""Check a drafted TAC report for the mistakes a reader cannot easily see.

Usage:
    check_draft.py DRAFT.md [--manifest WORK/manifest.json] [--max-numbers 6]

Fails (exit 1) on: a missing SPDX first line, a body citation [n] with no entry
in the Sources appendix, a dashboard link whose widget id is not in the
manifest (needs --manifest), and a missing "Data as of" date in the header.
Warns on: Sources entries nothing cites, empty sections, paragraphs packed with
numbers, and the count of [MAINTAINER INPUT] slots left for a human.
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs

SPDX = "[//]: # (SPDX-License-Identifier: CC-BY-4.0)"
SLOT = "[MAINTAINER INPUT]"
DASHBOARD = "hiero-hackers.github.io/analytics/#"
CITATION = re.compile(r"\[(\d+)\](?!\()")
ENTRY = re.compile(r"^\s*(?:[-*]\s+)?\[(\d+)\]")
LINK = re.compile(r"\]\(([^)\s]*)\)")
NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*%?")
YEAR = re.compile(r"^(?:19|20)\d{2}$")


def split_draft(lines: list[str]) -> tuple[list[str], list[str]]:
    """Split the lines into (body, sources-appendix) at the heading that names the Sources."""
    for i, line in enumerate(lines):
        if line.startswith("#") and "sources" in line.lower():
            return lines[:i], lines[i + 1 :]
    return lines, []


def count_numbers(paragraph: str) -> int:
    """Count the figures in a paragraph, ignoring citations, link targets, code and bare years."""
    text = CITATION.sub("", LINK.sub("]", re.sub(r"`[^`]*`", "", paragraph)))
    return sum(1 for n in NUMBER.findall(text) if not YEAR.match(n))


def widget_problems(body: list[str], manifest: dict) -> list[str]:
    """Return a message for each dashboard link whose widget id the manifest does not know."""
    out = []
    for n, line in enumerate(body, 1):
        for target in LINK.findall(line):
            if DASHBOARD not in target:
                continue
            params = parse_qs(target.split("#", 1)[1])
            widget, org = params.get("widget", [""])[0], params.get("org", [""])[0]
            entry = manifest.get("orgs", {}).get(org)
            known = {i["id"] for k in ("sections", "chart_sections", "views") for i in (entry or {}).get(k, [])}
            if widget and (entry is None or widget not in known):
                out.append(f"line {n}: widget '{widget}' is not an id of org '{org}' in the manifest")
    return out


def check(text: str, manifest: dict | None, max_numbers: int = 6) -> tuple[list[str], list[str]]:
    """Return (failures, warnings) for a draft."""
    lines = text.splitlines()
    body, appendix = split_draft(lines)
    fails: list[str] = []
    warns: list[str] = []
    if not lines or lines[0].strip() != SPDX:
        fails.append("line 1 must be the SPDX line: " + SPDX)
    if not any(re.search(r"data as of", line, re.I) for line in lines[:8]):
        fails.append('the header must say "Data as of <date>" within its first lines')
    cited = {int(m) for line in body for m in CITATION.findall(line)}
    entries = {int(m.group(1)) for line in appendix if (m := ENTRY.match(line))}
    fails += [f"[{n}] is cited but has no entry in the Sources appendix" for n in sorted(cited - entries)]
    warns += [f"Sources entry [{n}] is never cited" for n in sorted(entries - cited)]
    if manifest is not None:
        fails += widget_problems(body, manifest)
    warns += [
        f"section '{name}' is empty" for name, text_lines in sections(body) if not any(x.strip() for x in text_lines)
    ]
    for para in "\n".join(body).split("\n\n"):
        if not para.startswith("#") and count_numbers(para) > max_numbers:
            warns.append(f"{count_numbers(para)} numbers in one paragraph (max {max_numbers}): {para[:60]!r}")
    slots = text.count(SLOT)
    if slots:
        warns.append(f"{slots} {SLOT} slot(s) left for a maintainer")
    return fails, warns


def sections(body: list[str]) -> list[tuple[str, list[str]]]:
    """Return (heading, lines until the next heading) for each section of the body."""
    out: list[tuple[str, list[str]]] = []
    for line in body:
        if line.startswith("#"):
            out.append((line.lstrip("# ").strip(), []))
        elif out:
            out[-1][1].append(line)
    return [(name, lines) for name, lines in out]


def main(argv: list[str]) -> int:
    """Check the draft; print findings; exit 1 on any failure, 2 on unreadable input."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("draft", type=Path)
    ap.add_argument("--manifest", type=Path, help="manifest.json from `inventory.py fetch`, to check widget ids")
    ap.add_argument("--max-numbers", type=int, default=6)
    args = ap.parse_args(argv)
    try:
        text = args.draft.read_text(encoding="utf-8")
        manifest = json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest else None
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    fails, warns = check(text, manifest, args.max_numbers)
    for msg in fails:
        print(f"FAIL {msg}")
    for msg in warns:
        print(f"warn {msg}")
    print(f"{len(fails)} failure(s), {len(warns)} warning(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
