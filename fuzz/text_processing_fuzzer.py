"""Fuzz free-text parsers and spreadsheet-safe CSV transformation."""

import logging
import sys

import atheris

from hiero_analytics.domain.hip_references import extract_hip_mentions
from hiero_analytics.export.csv_safety import sanitize_csv_text
from hiero_analytics.pipelines.build_affiliations import parse_maintainers_md


def test_one_input(data: bytes) -> None:
    """Drive independent text parsers with bounded arbitrary Unicode."""
    provider = atheris.FuzzedDataProvider(data)
    title = provider.ConsumeUnicodeNoSurrogates(512)
    branch = provider.ConsumeUnicodeNoSurrogates(512)
    body = provider.ConsumeUnicodeNoSurrogates(2048)
    csv_text = provider.ConsumeUnicodeNoSurrogates(4096)
    markdown = provider.ConsumeUnicodeNoSurrogates(4096)

    extract_hip_mentions(title, branch, body)
    sanitized = sanitize_csv_text(csv_text)
    if sanitize_csv_text(sanitized) != sanitized:
        raise RuntimeError("CSV sanitization must be idempotent")
    list(parse_maintainers_md(markdown))


def main() -> None:
    """Start Atheris with libFuzzer-compatible arguments."""
    logging.disable(logging.CRITICAL)
    # PyInstaller's loader defeats import hooks, so instrument the loaded modules directly.
    atheris.instrument_all()
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
