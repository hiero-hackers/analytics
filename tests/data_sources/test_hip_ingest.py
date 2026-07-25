"""Tests for HIP-reference record hydration and inventory frontmatter parsing."""

from __future__ import annotations

from datetime import UTC, datetime

from hiero_analytics.data_sources.github_ingest.hip_references import parse_hip_frontmatter
from hiero_analytics.data_sources.models import HipReferenceRecord

CONTEXT = {"owner": "hiero-ledger", "repo": "hiero-sdk-java"}


def _pr_node(**overrides) -> dict:
    node = {
        "number": 42,
        "title": "feat: implement HIP-551 batch transactions",
        "body": "Per HIP-551. Also touches HIP-904 groundwork.",
        "headRefName": "feat/hip-551",
        "state": "MERGED",
        "createdAt": "2026-01-10T00:00:00Z",
        "mergedAt": "2026-01-20T00:00:00Z",
        "updatedAt": "2026-01-21T00:00:00Z",
        "author": {"login": "alice"},
    }
    node.update(overrides)
    return node


def test_from_github_node_yields_one_record_per_distinct_hip():
    """Each distinct HIP mention hydrates into its own record."""
    records = HipReferenceRecord.from_github_node(_pr_node(), CONTEXT)
    assert [r.hip for r in records] == [551, 904]
    r551 = records[0]
    assert r551.repo == "hiero-ledger/hiero-sdk-java"
    assert r551.match_sources == "title|branch|body"
    assert r551.author == "alice"
    assert r551.pr_state == "MERGED"
    assert r551.pr_merged_at == datetime(2026, 1, 20, tzinfo=UTC)
    assert records[1].match_sources == "body"


def test_from_github_node_marker_for_pr_without_mentions():
    """A PR citing no HIP still yields a marker record (watermark + denominator)."""
    records = HipReferenceRecord.from_github_node(
        _pr_node(title="fix: typo", body="small fix", headRefName="fix/typo"), CONTEXT
    )
    assert len(records) == 1
    marker = records[0]
    assert marker.hip is None
    assert marker.match_sources == ""
    assert marker.updated_at is not None


def test_from_github_node_open_pr_has_no_merged_at():
    """Open PRs hydrate with no merge timestamp."""
    records = HipReferenceRecord.from_github_node(_pr_node(state="OPEN", mergedAt=None), CONTEXT)
    assert all(r.pr_merged_at is None for r in records)
    assert all(r.pr_state == "OPEN" for r in records)


def test_from_github_node_null_body_and_author():
    """Null body and deleted author are handled defensively."""
    records = HipReferenceRecord.from_github_node(_pr_node(body=None, author=None), CONTEXT)
    assert [r.hip for r in records] == [551]
    assert records[0].author is None


GOOD_FRONTMATTER = """---
hip: 1056
title: Block Streams
author: >-
  Jasper Potts <@jasperpotts>, Richard Bair <@rbair23>
type: Standards Track
category: Core, Service, Mirror Node
status: Approved
created: 2023-06-04
updated: 2025-07-28
---

## Abstract
"""


def test_parse_hip_frontmatter_good_file():
    """A well-formed spec file parses into a full record."""
    record = parse_hip_frontmatter("hip-1056.md", GOOD_FRONTMATTER)
    assert record is not None
    assert record.number == 1056
    assert record.title == "Block Streams"
    assert record.status == "Approved"
    assert record.category == "Core, Service, Mirror Node"
    assert record.hip_type == "Standards Track"
    assert record.updated_at == datetime(2025, 7, 28, tzinfo=UTC)


def test_parse_hip_frontmatter_falls_back_to_created_date():
    """The watermark falls back to the created date when updated is absent."""
    text = "---\nhip: 21\ntitle: Free network info query\nstatus: Final\ncreated: 2021-06-09\n---\nbody"
    record = parse_hip_frontmatter("hip-21.md", text)
    assert record is not None
    assert record.updated == ""
    assert record.updated_at == datetime(2021, 6, 9, tzinfo=UTC)


def test_parse_hip_frontmatter_rejects_non_spec_files():
    """Templates and numberless documents are skipped, not errors."""
    assert parse_hip_frontmatter("template.md", "# Not a spec") is None
    assert parse_hip_frontmatter("draft.md", "---\ntitle: no number\n---\nbody") is None
    assert parse_hip_frontmatter("weird.md", "---\nhip: TBD\n---\nbody") is None


def test_parse_hip_frontmatter_unparseable_yaml_is_skipped():
    """Broken YAML frontmatter is skipped with a warning."""
    text = "---\nhip: [unclosed\n---\nbody"
    assert parse_hip_frontmatter("bad.md", text) is None


def test_from_github_node_body_only_cue_is_qualified():
    """A body-only mention behind a distancing cue hydrates with the qualifier."""
    node = _pr_node(
        title="fix: retry logic",
        headRefName="fix/retries",
        body="Interim fix; we are waiting on HIP-991 for the real solution.",
    )
    (record,) = HipReferenceRecord.from_github_node(node, CONTEXT)
    assert record.hip == 991
    assert record.match_sources == "body"
    assert record.qualifier == "waiting on"


def test_parse_hip_frontmatter_release_field():
    """The release number HIP-1 requires of Final specs is captured."""
    text = "---\nhip: 904\ntitle: Frictionless Airdrops\nstatus: Final\nrelease: v0.56\ncreated: 2024-02-25\n---\nbody"
    record = parse_hip_frontmatter("hip-904.md", text)
    assert record is not None
    assert record.release == "v0.56"
