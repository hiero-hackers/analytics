"""Regression tests for label classification rules."""

from hiero_analytics.domain.labels import (
    DIFFICULTY_ADVANCED,
    DIFFICULTY_BEGINNER,
    DIFFICULTY_GOOD_FIRST_ISSUE,
    DIFFICULTY_INTERMEDIATE,
)


def test_difficulty_specs_match_skill_label_variants():
    """Difficulty specs should accept the SDK `skill:` label variants."""
    assert DIFFICULTY_GOOD_FIRST_ISSUE.matches({"skill: good first issue"})
    assert DIFFICULTY_BEGINNER.matches({"skill: beginner"})
    assert DIFFICULTY_INTERMEDIATE.matches({"skill: intermediate"})
    assert DIFFICULTY_ADVANCED.matches({"skill: advanced"})


def test_difficulty_specs_match_case_insensitively():
    """Difficulty specs should normalize labels before matching."""
    assert DIFFICULTY_BEGINNER.matches({"Skill: Beginner"})
    assert DIFFICULTY_INTERMEDIATE.matches({"Skill: Intermediate"})
    assert DIFFICULTY_ADVANCED.matches({"Skill: Advanced"})
