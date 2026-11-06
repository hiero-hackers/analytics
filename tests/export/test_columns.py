"""Tests for column declaration normalization in export/columns.py."""

from __future__ import annotations

import pytest

from hiero_analytics.export.columns import Column, column_spec


def test_column_spec_from_column_instance():
    """A Column serializes with all its fields."""
    column = Column("repo", "Repo", format="text", description="The repo name.")

    assert column_spec(column) == {
        "key": "repo",
        "label": "Repo",
        "format": "text",
        "description": "The repo name.",
    }


@pytest.mark.parametrize(
    ("declaration", "expected"),
    [
        (("a", "A"), {"key": "a", "label": "A"}),
        (("a", "A", "number"), {"key": "a", "label": "A", "format": "number"}),
        (
            ["a", "A", "number", "Desc"],
            {"key": "a", "label": "A", "format": "number", "description": "Desc"},
        ),
        (("a", "A", None, "Desc"), {"key": "a", "label": "A", "description": "Desc"}),
        (("a", "A", "", ""), {"key": "a", "label": "A"}),
    ],
)
def test_column_spec_from_tuple_or_list(declaration, expected):
    """Tuples and lists of 2-4 items serialize, dropping empty fields."""
    assert column_spec(declaration) == expected


def test_column_spec_reads_positions_not_iteration():
    """A tuple subclass with a custom iterator is still read by position."""

    class OddTuple(tuple):
        def __iter__(self):
            return iter(())

    assert column_spec(OddTuple(("a", "A", "number", "Desc"))) == {
        "key": "a",
        "label": "A",
        "format": "number",
        "description": "Desc",
    }


@pytest.mark.parametrize("declaration", [("a",), ("a", "A", "f", "d", "extra"), ()])
def test_column_spec_rejects_bad_length(declaration):
    """Declarations with the wrong number of items raise ValueError."""
    with pytest.raises(ValueError, match="expected 2, 3, or 4"):
        column_spec(declaration)


def test_column_spec_rejects_other_types():
    """Anything that is not a Column, tuple or list raises TypeError."""
    with pytest.raises(TypeError, match="expected a Column"):
        column_spec("ab")
