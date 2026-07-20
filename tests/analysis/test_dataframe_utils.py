"""Tests for the dataframe utility helpers."""

import pandas as pd

from hiero_analytics.analysis.dataframe_utils import filter_by_labels, records_to_dataframe


def test_records_to_dataframe_maps_each_record_to_a_row():
    """Each record becomes one row via the mapper."""
    df = records_to_dataframe(
        [1, 2, 3],
        lambda n: {"n": n, "sq": n * n},
        ["n", "sq"],
    )

    assert list(df.columns) == ["n", "sq"]
    assert df["n"].tolist() == [1, 2, 3]
    assert df["sq"].tolist() == [1, 4, 9]


def test_records_to_dataframe_skips_records_mapped_to_none():
    """A mapper returning None drops that record."""
    df = records_to_dataframe(
        [1, 2, 3, 4],
        lambda n: None if n % 2 == 0 else {"n": n},
        ["n"],
    )

    assert df["n"].tolist() == [1, 3]


def test_records_to_dataframe_empty_input_returns_column_schema():
    """Empty input yields an empty frame carrying the given columns."""
    df = records_to_dataframe([], lambda r: {"a": r}, ["a", "b"])

    assert df.empty
    assert list(df.columns) == ["a", "b"]


def test_records_to_dataframe_all_skipped_returns_column_schema():
    """When every record is skipped, the empty frame still carries the columns."""
    df = records_to_dataframe(
        [2, 4, 6],
        lambda _n: None,
        ["n"],
    )

    assert df.empty
    assert list(df.columns) == ["n"]


def test_filter_by_labels_matches_case_insensitively():
    """Mixed-case issue labels match a lowercased label set (as built by LabelSpec)."""
    df = pd.DataFrame(
        {
            "number": [1, 2, 3],
            "labels": [["Good First Issue"], ["bug"], ["skill: Good First Issue"]],
        }
    )

    result = filter_by_labels(df, {"good first issue", "skill: good first issue"})

    assert result["number"].tolist() == [1, 3]


def test_filter_by_labels_handles_missing_labels_and_empty_frame():
    """Rows with None labels never match, and an empty frame passes through."""
    df = pd.DataFrame({"number": [1, 2], "labels": [None, ["Bug"]]})

    result = filter_by_labels(df, {"bug"})

    assert result["number"].tolist() == [2]
    assert filter_by_labels(df.iloc[0:0], {"bug"}).empty
