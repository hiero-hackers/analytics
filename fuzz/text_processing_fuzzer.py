"""Fuzz free-text parsers and spreadsheet-safe CSV transformation."""

import logging
import sys

import atheris

from hiero_analytics.domain.hip_references import extract_hip_mentions
from hiero_analytics.export.csv_safety import sanitize_csv_text
from hiero_analytics.pipelines.build_affiliations import parse_maintainers_md


def test_one_input(data: bytes) -> None:
    """Drive independent text parsers with bounded arbitrary Unicode."""
    # Decode raw input rather than FuzzedDataProvider so seed files survive intact.
    text = data.decode("utf-8", errors="replace")

    extract_hip_mentions(text, text, text)
    sanitized = sanitize_csv_text(text)
    if sanitize_csv_text(sanitized) != sanitized:
        raise RuntimeError("CSV sanitization must be idempotent")
    list(parse_maintainers_md(text))


def main() -> None:
    """Start Atheris with libFuzzer-compatible arguments."""
    logging.disable(logging.CRITICAL)
    # PyInstaller's loader defeats import hooks, so instrument the loaded modules directly.
    atheris.instrument_all()
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
