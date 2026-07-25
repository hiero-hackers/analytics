"""Recognizing HIP references in free text (PR titles, branch names, bodies).

Contributors are inconsistent about how they cite a HIP — ``HIP-1200``,
``HIP 1200``, ``hip_1200``, ``HIP #1200``, ``hip1200``, and URL forms like
``hips.hedera.com/hip/hip-1200`` all occur in real PRs — so matching is done
here, locally and case-insensitively, rather than through GitHub search (whose
tokenizer misses several of these variants). Bare issue references (``#1200``)
deliberately never match: a number only counts with an explicit ``hip`` marker.

Extraction is purely mechanical and does **not** validate numbers against the
HIP inventory — validation is an analysis-time concern, so unknown numbers can
be surfaced for review instead of silently dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# \bhip guards against chip/ship/whip (no word boundary inside those words);
# [-_\s#]* absorbs every separator variant seen in the wild, including none.
_HIP_MENTION = re.compile(r"\bhips?[-_\s#]*(\d{1,4})\b", re.IGNORECASE)

# Order defines source precedence in ``HipMention.sources`` and snippets: a
# title mention is the strongest signal, then the branch name, then the body.
_SOURCE_ORDER = ("title", "branch", "body")

_SNIPPET_CONTEXT = 40
_SNIPPET_MAX = 160

# Distancing cues: phrases that, immediately before a body mention, signal the
# PR talks *about* the HIP rather than implementing it ("waiting on HIP-991",
# "prepares for HIP-1195"). Deliberately conservative — a missed cue leaves an
# auditable extra row, while an over-broad cue silently hides real work. Title
# and branch mentions are never qualified: nobody names a branch feat/hip-551
# to say they are waiting on it.
_DISTANCING_CUES = (
    "waiting on",
    "waiting for",
    "wait for",
    "waits on",
    "blocked by",
    "blocked on",
    "blocked until",
    "depends on",
    "dependent on",
    "prepare for",
    "prepares for",
    "preparing for",
    "preparation for",
    "groundwork for",
    "ahead of",
    "in anticipation of",
    "prerequisite for",
    "placeholder for",
    "superseded by",
    "replaced by",
)
_CUE_WINDOW = 50  # characters before the mention scanned for a cue


@dataclass(frozen=True)
class HipMention:
    """One distinct HIP number mentioned by a PR, with its evidence.

    ``qualifier`` carries the distancing cue found before the mention when the
    *only* place the number appears is the PR body — the mechanical signal
    that the PR references the HIP without implementing it. Empty otherwise.
    """

    number: int
    sources: tuple[str, ...]  # subset of ("title", "branch", "body"), in that order
    snippet: str  # text surrounding the first sighting, whitespace-collapsed
    qualifier: str = ""


def _snippet(text: str, match: re.Match) -> str:
    """Context around ``match``, collapsed to one line for CSV friendliness."""
    start = max(0, match.start() - _SNIPPET_CONTEXT)
    raw = text[start : match.end() + _SNIPPET_CONTEXT]
    return " ".join(raw.split())[:_SNIPPET_MAX]


def _distancing_cue(text: str, match: re.Match) -> str:
    """The distancing cue preceding ``match``, or "" when none is found."""
    window = " ".join(text[max(0, match.start() - _CUE_WINDOW) : match.start()].lower().split())
    for cue in _DISTANCING_CUES:
        if cue in window:
            return cue
    return ""


def extract_hip_mentions(title: str, branch: str, body: str) -> list[HipMention]:
    """Every distinct HIP number mentioned across ``title``/``branch``/``body``.

    Each number is reported once, with the union of sources it appeared in and
    a snippet from the highest-precedence source that mentioned it. A number
    seen *only* in the body keeps the distancing cue (if any) of its first
    body occurrence as ``qualifier``. Results are ordered by HIP number for
    deterministic output.
    """
    sources: dict[int, list[str]] = {}
    snippets: dict[int, str] = {}
    body_cues: dict[int, str] = {}
    for source, text in zip(_SOURCE_ORDER, (title, branch, body), strict=True):
        for match in _HIP_MENTION.finditer(text or ""):
            number = int(match.group(1))
            sources.setdefault(number, []).append(source)
            snippets.setdefault(number, _snippet(text, match))
            if source == "body" and number not in body_cues:
                body_cues[number] = _distancing_cue(text, match)
    mentions = []
    for number, found in sorted(sources.items()):
        unique = tuple(dict.fromkeys(found))
        body_only = set(unique) == {"body"}
        mentions.append(
            HipMention(
                number=number,
                sources=unique,
                snippet=snippets[number],
                qualifier=body_cues.get(number, "") if body_only else "",
            )
        )
    return mentions
