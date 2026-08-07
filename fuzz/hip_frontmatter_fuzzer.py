"""Fuzz the HIP proposal frontmatter parser with arbitrary repository content."""

import logging
import sys

import atheris

from hiero_analytics.data_sources.github_ingest.hip_references import parse_hip_frontmatter


def test_one_input(data: bytes) -> None:
    """Exercise frontmatter parsing; malformed input must be handled without crashing."""
    text = data.decode("utf-8", errors="replace")
    parse_hip_frontmatter("fuzzed.md", text)


def main() -> None:
    """Start Atheris with libFuzzer-compatible arguments."""
    logging.disable(logging.CRITICAL)
    # PyInstaller's loader defeats import hooks, so instrument the loaded modules directly.
    atheris.instrument_all()
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
