#!/usr/bin/env python3
"""Export the TAC draft's figures to PNG and the draft itself to a review PDF.

The markdown file is what the TAC files; this script only produces the
companions a maintainer needs: PNG figures (GitHub attachments do not accept
SVG) and a PDF review copy for circulating to the TSC. It adds nothing to
the project: it uses whichever converter the machine already has and says
plainly when there is none.

Usage:
    export_report.py png  FIGURES_DIR [--width 1920]
    export_report.py pdf  DRAFT.md [--out DRAFT.pdf]

``png`` converts every ``*.svg`` in FIGURES_DIR with the first available of
rsvg-convert, ImageMagick (``magick``), Inkscape.

``pdf`` renders the markdown to HTML (the ``markdown`` package, fetched
transiently through ``uv run --with markdown`` when not installed), swaps
``figures/*.svg`` references for the PNGs, and prints it with headless
Chrome or Chromium.
"""

from __future__ import annotations

import argparse
import glob
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
]

PRINT_CSS = """
@page { size: A4; margin: 18mm 16mm; }
body { font: 11pt/1.45 Georgia, 'Times New Roman', serif; color: #111; max-width: 100%; }
h1 { font-size: 20pt; margin: 0 0 6pt; }
h2 { font-size: 15pt; margin: 18pt 0 6pt; border-bottom: 1px solid #999; }
h3 { font-size: 12.5pt; margin: 14pt 0 4pt; }
p, li { orphans: 3; widows: 3; }
blockquote { border-left: 3px solid #c60; background: #fff7ee; margin: 8pt 0; padding: 4pt 10pt; }
table { border-collapse: collapse; font-size: 9.5pt; margin: 6pt 0; }
tr { page-break-inside: avoid; }
h2, h3 { page-break-after: avoid; }
th, td { border: 1px solid #bbb; padding: 3pt 6pt; vertical-align: top; }
th { background: #eee; }
img { max-width: 100%; page-break-inside: avoid; }
code { font: 9.5pt Menlo, Consolas, monospace; word-break: break-all; }
pre { white-space: pre-wrap; font-size: 9pt; background: #f4f4f4; padding: 6pt; }
.source { font-size: 9pt; color: #444; }
"""


def _first_tool(names: list[str]) -> str | None:
    for n in names:
        path = n if os.path.isabs(n) and os.path.exists(n) else shutil.which(n)
        if path:
            return path
    return None


def cmd_png(figures_dir: str, width: int) -> int:
    """Convert every SVG in the directory to a PNG beside it."""
    svgs = sorted(glob.glob(os.path.join(figures_dir, "*.svg")))
    if not svgs:
        print(f"no .svg files in {figures_dir}", file=sys.stderr)
        return 2
    tool = _first_tool(["rsvg-convert", "magick", "inkscape"])
    if not tool:
        print(
            "no SVG converter found (rsvg-convert, magick or inkscape). Tell the maintainer to "
            "export PNGs from the dashboard's print button, or install librsvg (brew install librsvg).",
            file=sys.stderr,
        )
        return 3
    for svg in svgs:
        png = svg[:-4] + ".png"
        base = os.path.basename(tool)
        if base == "rsvg-convert":
            run = [tool, "-w", str(width), svg, "-o", png]
        elif base == "magick":
            run = [tool, "-density", "200", svg, "-resize", f"{width}x", png]
        else:
            run = [tool, svg, f"--export-width={width}", f"--export-filename={png}"]
        subprocess.run(run, check=True)  # noqa: S603 - argv list, tool path resolved above
        print(png)
    return 0


def _markdown_to_html(text: str) -> str:
    try:
        import markdown  # type: ignore

        return markdown.markdown(text, extensions=["tables", "fenced_code"])
    except ImportError:
        if not shutil.which("uv"):
            raise SystemExit("the 'markdown' package is not installed and uv is not available to fetch it") from None
        proc = subprocess.run(  # noqa: S603 - fixed argv
            [  # noqa: S607 - uv resolved from PATH on purpose
                "uv",
                "run",
                "--no-project",
                "--with",
                "markdown",
                "python",
                "-c",
                "import sys, markdown; sys.stdout.write(markdown.markdown(sys.stdin.read(), extensions=['tables','fenced_code']))",
            ],
            input=text,
            capture_output=True,
            text=True,
            check=True,
        )
        return proc.stdout


def cmd_pdf(draft: str, out: str | None) -> int:
    """Render the draft to HTML with the PNG figures and print it to PDF."""
    chrome = _first_tool(CHROME_CANDIDATES)
    if not chrome:
        print("no Chrome or Chromium found; open the draft in a browser and print to PDF by hand.", file=sys.stderr)
        return 3
    out = out or os.path.splitext(draft)[0] + ".pdf"
    with open(draft, encoding="utf-8") as fh:
        text = fh.read()
    # Drop the SPDX comment line (it renders as text in HTML) and prefer PNG figures.
    text = re.sub(r"^\[//\]: # \(.*\)\n", "", text, count=1, flags=re.M)
    text = re.sub(r"\((figures/[^)]+)\.svg\)", r"(\1.png)", text)
    body = _markdown_to_html(text)
    body = re.sub(r"<p>(Source:.*?)</p>", r"<p class='source'>\1</p>", body, flags=re.S)
    title = re.search(r"^# (.+)$", text, flags=re.M)
    page = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title.group(1) if title else os.path.basename(draft))}</title>"
        f"<style>{PRINT_CSS}</style></head><body>{body}</body></html>"
    )
    draft_dir = os.path.dirname(os.path.abspath(draft))
    with tempfile.NamedTemporaryFile("w", suffix=".html", dir=draft_dir, delete=False, encoding="utf-8") as tmp:
        tmp.write(page)
        html_path = tmp.name
    try:
        subprocess.run(  # noqa: S603 - argv list, chrome path resolved above
            [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--no-pdf-header-footer",
                f"--print-to-pdf={os.path.abspath(out)}",
                "file://" + html_path,
            ],
            check=True,
            capture_output=True,
        )
    finally:
        os.unlink(html_path)
    print(out)
    return 0


def main(argv: list[str]) -> int:
    """Dispatch to the png or pdf exporter."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("png")
    p.add_argument("figures_dir")
    p.add_argument("--width", type=int, default=1920)
    q = sub.add_parser("pdf")
    q.add_argument("draft")
    q.add_argument("--out")
    a = ap.parse_args(argv)
    if a.cmd == "png":
        return cmd_png(a.figures_dir, a.width)
    return cmd_pdf(a.draft, a.out)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
