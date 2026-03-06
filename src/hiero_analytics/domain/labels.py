from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LabelSpec:
    """
    Represents a logical label group used for analytics.
    """

    name: str
    labels: set[str]

    def __or__(self, other: "LabelSpec") -> "LabelSpec":
        """
        Combine label groups.
        """

        return LabelSpec(
            name=f"{self.name} + {other.name}",
            labels=self.labels | other.labels,
        )


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

BUG = LabelSpec(
    name="Bug Reports",
    labels={"bug"},
)

DIFFICULTY_GOOD_FIRST_ISSUE = LabelSpec(
    name="Good First Issue",
    labels={
        "Good First Issue",
        "skill: Good First Issue",
    },
)

DIFFICULTY_BEGINNER = LabelSpec(
    name="Beginner",
    labels={
        "beginner",
    },
)

DIFFICULTY_INTERMEDIATE = LabelSpec(
    name="Intermediate",
    labels={
        "intermediate",
    },
)

DIFFICULTY_ADVANCED = LabelSpec(
    name="Advanced",
    labels={
        "advanced",
    },
)