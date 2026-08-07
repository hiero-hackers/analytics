"""Fuzz the HIP proposal frontmatter parser with arbitrary repository content."""

import logging
import sys

import atheris

with atheris.instrument_imports():
    from hiero_analytics.data_sources.github_ingest.hip_references import parse_hip_frontmatter

atheris.instrument_func(parse_hip_frontmatter)


@atheris.instrument_func
def test_one_input(data: bytes) -> None:
    """Exercise frontmatter parsing; malformed input must be handled without crashing."""
    text = data.decode("utf-8", errors="replace")
    parse_hip_frontmatter("fuzzed.md", text)


def main() -> None:
    """Start Atheris with libFuzzer-compatible arguments."""
    logging.disable(logging.CRITICAL)
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
