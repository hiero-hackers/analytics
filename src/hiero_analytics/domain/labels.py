"""Label group definitions used throughout analytics classification."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LabelSpec:
    """Represent a logical label group used for analytics."""

    name: str
    labels: set[str]

    def __post_init__(self):
        """Normalize labels for case-insensitive matching."""
        object.__setattr__(
            self,
            "labels",
            {label.lower() for label in self.labels},
        )

    def __or__(self, other: LabelSpec) -> LabelSpec:
        """Combine label groups."""
        return LabelSpec(
            name=f"{self.name} + {other.name}",
            labels=self.labels | other.labels,
        )

    def matches(self, labels: set[str]) -> bool:
        """
        Return True if any of the given labels matches this spec's labels.

        The input is a set of label names; matching is case-insensitive and
        succeeds when there is at least one common label.
        """
        normalized = {label.lower() for label in labels}
        return bool(normalized & self.labels)


GOOD_FIRST_ISSUE = LabelSpec(
    name="Good First Issues",
    labels={
        "good first issue",
        "skill: good first issue",
    },
)

GOOD_FIRST_ISSUE_CANDIDATE = LabelSpec(
    name="Good First Issue Candidates",
    labels={
        "good first issue candidate",
    },
)

ALL_ONBOARDING = GOOD_FIRST_ISSUE | GOOD_FIRST_ISSUE_CANDIDATE

# Same label set as the onboarding spec, singular display name for the
# difficulty charts — derived so the two analyses can't drift apart.
DIFFICULTY_GOOD_FIRST_ISSUE = LabelSpec(name="Good First Issue", labels=GOOD_FIRST_ISSUE.labels)

DIFFICULTY_BEGINNER = LabelSpec(
    name="Beginner",
    labels={
        "beginner",
        "skill: beginner",
    },
)

DIFFICULTY_INTERMEDIATE = LabelSpec(
    name="Intermediate",
    labels={
        "intermediate",
        "skill: intermediate",
    },
)

DIFFICULTY_ADVANCED = LabelSpec(
    name="Advanced",
    labels={
        "advanced",
        "skill: advanced",
    },
)

DIFFICULTY_LEVELS = (
    DIFFICULTY_GOOD_FIRST_ISSUE,
    DIFFICULTY_BEGINNER,
    DIFFICULTY_INTERMEDIATE,
    DIFFICULTY_ADVANCED,
)

UNKNOWN_DIFFICULTY = "Unknown"

DIFFICULTY_ORDER = [
    UNKNOWN_DIFFICULTY,
    DIFFICULTY_GOOD_FIRST_ISSUE.name,
    DIFFICULTY_BEGINNER.name,
    DIFFICULTY_INTERMEDIATE.name,
    DIFFICULTY_ADVANCED.name,
]
