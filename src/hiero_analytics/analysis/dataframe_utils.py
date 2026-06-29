"""Generic dataframe helpers for converting and filtering records."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

import pandas as pd

from hiero_analytics.data_sources.models import IssueRecord, RepositoryRecord


def repos_to_dataframe(records: list[RepositoryRecord]) -> pd.DataFrame:
    """
    Convert RepositoryRecord objects into a DataFrame.

    Columns produced:
        repo        Full repository name (owner/name)
        pushed_at   Timestamp of the last push (or None)
        language    Primary language (or None)
    """
    return records_to_dataframe(
        records,
        lambda record: {
            "repo": record.full_name,
            "pushed_at": record.pushed_at,
            "language": record.language,
        },
        ["repo", "pushed_at", "language"],
    )

# PEP 695 type parameters are intentionally avoided here because the package
# supports Python 3.11.
T = TypeVar("T")


def records_to_dataframe(  # noqa: UP047
    records: Sequence[T],
    mapper: Callable[[T], dict[str, object] | None],
    columns: Sequence[str],
) -> pd.DataFrame:
    """Convert a list of records into a DataFrame via a per-record mapper.

    ``mapper`` returns a column-name -> value dict for each record, or
    ``None`` to skip that record. When no rows are produced (empty input or
    every record skipped) an empty DataFrame carrying ``columns`` is returned,
    so downstream code always sees a stable schema.

    Parameters
    ----------
    records
        Records to convert (any dataclass record type).
    mapper
        Maps one record to a row dict, or returns ``None`` to drop it.
    columns
        Column schema used for the empty-result DataFrame.

    Returns:
    -------
    pd.DataFrame
        One row per non-skipped record, or an empty frame with ``columns``.
    """
    rows = [row for record in records if (row := mapper(record)) is not None]
    if not rows:
        return pd.DataFrame(columns=list(columns))
    return pd.DataFrame(rows)


def issues_to_dataframe(issues: list[IssueRecord]) -> pd.DataFrame:
    """
    Convert a collection of IssueRecord objects into a Pandas DataFrame.

    The resulting dataframe contains a normalized tabular representation
    of issue metadata suitable for analytical operations such as filtering,
    grouping, and aggregation.

    Columns produced:
        repo        Repository name
        number      Issue number
        state       Issue state (e.g. "open", "closed")
        created_at  Issue creation timestamp
        year        Year extracted from created_at
        labels      List of issue labels

    Parameters
    ----------
    issues
        List of IssueRecord objects retrieved from the data source layer.

    Returns:
    -------
    pd.DataFrame
        DataFrame containing one row per issue.
    """
    return pd.DataFrame(
        [
            {
                "repo": issue.repo,
                "number": issue.number,
                "state": issue.state.lower(),
                "created_at": issue.created_at,
                "year": issue.created_at.year,
                "labels": issue.labels,
            }
            for issue in issues
        ]
    )


def filter_by_labels(df: pd.DataFrame, labels: set[str]) -> pd.DataFrame:
    """
    Filter issues that contain at least one label from a given label set.

    This function performs a set intersection between the labels attached
    to each issue and the provided label set.

    Parameters
    ----------
    df
        DataFrame produced by `issues_to_dataframe`.
    labels
        Set of label names to filter for.

    Returns:
    -------
    pd.DataFrame
        Subset of the dataframe containing only issues with matching labels.
    """
    if df.empty:
        return df.copy()

    return df[df["labels"].map(lambda xs: bool(set(xs or []) & labels))]


def count_by(df: pd.DataFrame, *cols: str) -> pd.DataFrame:
    """
    Aggregate issue counts by one or more columns.

    Performs a group-by operation over the specified columns and returns
    the number of issues in each group.

    Parameters
    ----------
    df
        DataFrame produced by `issues_to_dataframe`.
    *cols
        One or more column names to group by.

    Returns:
    -------
    pd.DataFrame
        DataFrame containing the grouping columns and a `count` column
        representing the number of issues in each group.
    """
    if df.empty:
        return pd.DataFrame(columns=[*cols, "count"])

    return (
        df.groupby(list(cols))
        .size()
        .reset_index(name="count")
        .sort_values(list(cols))
    )