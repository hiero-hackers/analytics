"""Fuzz GraphQL payload traversal and record hydration from GitHub responses."""

import json
import logging
import sys

import atheris

from hiero_analytics.data_sources.models import (
    ContributorActivityRecord,
    HipReferenceRecord,
    IssueRecord,
    IssueTimelineEventRecord,
    PullRequestDifficultyRecord,
    RepositoryRecord,
)
from hiero_analytics.data_sources.pagination import extract_graphql_cursor_page
from hiero_analytics.data_sources.rate_limit import RateLimitSnapshot

# Malformed nodes are rejected by design: missing keys raise KeyError, and
# strict timestamp parsing raises ValueError/TypeError. Any other exception
# indicates a real defect.
EXPECTED_REJECTIONS = (KeyError, TypeError, ValueError)

RECORD_TYPES = (
    RepositoryRecord,
    IssueRecord,
    IssueTimelineEventRecord,
    PullRequestDifficultyRecord,
    HipReferenceRecord,
    ContributorActivityRecord,
)


@atheris.instrument_func
def test_one_input(data: bytes) -> None:
    """Feed arbitrary JSON payloads through traversal and hydration helpers."""
    provider = atheris.FuzzedDataProvider(data)
    try:
        payload = json.loads(provider.ConsumeUnicodeNoSurrogates(8192))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return
    if not isinstance(payload, dict):
        return

    extract_graphql_cursor_page(payload, ["repository", "pullRequests"])
    RateLimitSnapshot.from_graphql_payload(payload)

    headers = payload.get("headers")
    if isinstance(headers, dict):
        RateLimitSnapshot.from_rest_headers({str(key): str(value) for key, value in headers.items()})

    node = payload.get("node")
    context = payload.get("context")
    if not isinstance(node, dict) or not isinstance(context, dict):
        return
    for record_type in RECORD_TYPES:
        try:
            record_type.from_github_node(node, context)
        except EXPECTED_REJECTIONS:
            continue


def main() -> None:
    """Start Atheris with libFuzzer-compatible arguments."""
    logging.disable(logging.CRITICAL)
    # PyInstaller's loader defeats import hooks, so instrument the loaded modules directly.
    atheris.instrument_all()
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
