"""Unit tests for HIP-mention extraction from PR text."""

from __future__ import annotations

import pytest

from hiero_analytics.domain.hip_references import extract_hip_mentions


def _numbers(title: str = "", branch: str = "", body: str = "") -> list[int]:
    return [m.number for m in extract_hip_mentions(title, branch, body)]


@pytest.mark.parametrize(
    "text",
    [
        "HIP-1200: add thing",
        "HIP 1200 support",
        "hip_1200 groundwork",
        "Implement HIP #1200",
        "hip1200 follow-up",
        "see https://hips.hedera.com/hip/hip-1200 for details",
        "docs: link HIP/hip-1200.md",
        "HIPs 1200 and friends",  # plural marker
    ],
)
def test_naming_variants_match(text: str):
    """Every naming variant observed in real PRs resolves to the number."""
    assert _numbers(title=text) == [1200]


@pytest.mark.parametrize(
    "text",
    [
        "chip-1200 firmware",  # no word boundary → not a HIP
        "shipping 42 crates",
        "whip 99",
        "fixes #1200",  # bare issue reference must never match
        "HIP with no number",
        "hip-",
    ],
)
def test_non_references_do_not_match(text: str):
    """Lookalikes and bare issue numbers never count as HIP references."""
    assert _numbers(title=text, body=text) == []


def test_sources_are_unioned_in_precedence_order():
    """A number cited in several places reports each source once, title first."""
    mentions = extract_hip_mentions(
        title="feat: implement HIP-551",
        branch="feat/hip-551-batch",
        body="Adds batch transactions per HIP-551.",
    )
    assert len(mentions) == 1
    assert mentions[0].sources == ("title", "branch", "body")


def test_distinct_numbers_reported_separately_and_sorted():
    """Different numbers become separate mentions, ordered numerically."""
    mentions = extract_hip_mentions(
        title="HIP-904 airdrops",
        branch="",
        body="Groundwork shared with HIP-551.",
    )
    assert [m.number for m in mentions] == [551, 904]
    assert mentions[0].sources == ("body",)
    assert mentions[1].sources == ("title",)


def test_snippet_carries_surrounding_context_from_strongest_source():
    """The snippet comes from the highest-precedence citing source."""
    mentions = extract_hip_mentions(
        title="",
        branch="feat/hip-1023",
        body="Implements the flow described in HIP-1023 for scheduled work.\nMore text.",
    )
    # Branch outranks body, so the snippet comes from the branch name.
    assert mentions[0].snippet == "feat/hip-1023"


def test_snippet_is_single_line():
    """Snippets collapse newlines for CSV friendliness."""
    body = "line one\nrefs HIP-777 here\nline three"
    (mention,) = extract_hip_mentions("", "", body)
    assert "\n" not in mention.snippet
    assert "HIP-777" in mention.snippet


def test_empty_and_none_like_inputs():
    """Empty inputs yield no mentions."""
    assert extract_hip_mentions("", "", "") == []


def test_body_only_mention_behind_distancing_cue_is_qualified():
    """A body-only mention preceded by a distancing phrase carries the cue."""
    (mention,) = extract_hip_mentions("", "", "We cannot do more, we are waiting on HIP-991 to land.")
    assert mention.qualifier == "waiting on"
    (mention,) = extract_hip_mentions("", "", "This helps to prepare for HIP-1195 hooks.")
    assert mention.qualifier == "prepare for"


def test_title_or_branch_mention_is_never_qualified():
    """A title/branch mention overrides any distancing phrase in the body."""
    (mention,) = extract_hip_mentions("feat: HIP-551 batch transactions", "", "Was blocked by HIP-551 until now.")
    assert mention.qualifier == ""
    (mention,) = extract_hip_mentions("", "feat/hip-551", "waiting on HIP-551")
    assert mention.qualifier == ""


def test_plain_body_mention_is_not_qualified():
    """A body mention with no distancing phrase counts as implementation evidence."""
    (mention,) = extract_hip_mentions("", "", "Implements the fee logic from HIP-1261.")
    assert mention.qualifier == ""


def test_cue_must_be_near_the_mention():
    """A distancing phrase far from the mention does not qualify it."""
    body = "We were waiting on reviews for a while. " + "x" * 80 + " Implements HIP-777."
    (mention,) = extract_hip_mentions("", "", body)
    assert mention.qualifier == ""
