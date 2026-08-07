"""Fuzz record deserialization and the serialize/deserialize round trip."""

import json
import logging
import sys

import atheris

from hiero_analytics.data_sources.models import (
    ContributorActivityRecord,
    HipReferenceRecord,
    HipSpecRecord,
    IssueRecord,
    IssueTimelineEventRecord,
    PullRequestDifficultyRecord,
    RepositoryRecord,
)
from hiero_analytics.data_sources.serialization import (
    deserialize_record,
    parse_github_datetime,
    serialize_record,
)

# A corrupted payload is rejected by design: unexpected or missing fields raise
# TypeError, and malformed datetimes raise ValueError.
EXPECTED_REJECTIONS = (TypeError, ValueError)

RECORD_TYPES = (
    RepositoryRecord,
    IssueRecord,
    IssueTimelineEventRecord,
    PullRequestDifficultyRecord,
    HipReferenceRecord,
    HipSpecRecord,
    ContributorActivityRecord,
)


@atheris.instrument_func
def test_one_input(data: bytes) -> None:
    """Deserialize arbitrary payloads and verify the round trip when one succeeds."""
    provider = atheris.FuzzedDataProvider(data)
    parse_github_datetime(provider.ConsumeUnicodeNoSurrogates(64))

    try:
        payload = json.loads(provider.ConsumeUnicodeNoSurrogates(4096))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return
    if not isinstance(payload, dict):
        return

    for record_type in RECORD_TYPES:
        try:
            record = deserialize_record(record_type, dict(payload))
        except EXPECTED_REJECTIONS:
            continue
        if deserialize_record(record_type, serialize_record(record)) != record:
            raise RuntimeError(f"{record_type.__name__} failed to round-trip")


def main() -> None:
    """Start Atheris with libFuzzer-compatible arguments."""
    logging.disable(logging.CRITICAL)
    # PyInstaller's loader defeats import hooks, so instrument the loaded modules directly.
    atheris.instrument_all()
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
