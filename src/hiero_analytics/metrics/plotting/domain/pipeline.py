from __future__ import annotations

from pathlib import Path
import pandas as pd

from ..bars import plot_bar
from ..lines import plot_line
from ..stacked_bars import plot_stacked_bar


def plot_label_yearly_trend(
    df: pd.DataFrame,
    title: str,
    output_path: Path,
) -> None:
    """
    Plot labe   l trend over time.
    """

    if df.empty:
        return

    plot_line(
        df,
        x_col="year",
        y_col="count",
        title=title,
        output_path=output_path,
    )


def plot_label_total_by_repo(
    df: pd.DataFrame,
    title: str,
    output_path: Path,
) -> None:
    """
    Plot total label occurrences by repository.
    """

    if df.empty:
        return

    plot_bar(
        df,
        x_col="repo",
        y_col="count",
        title=title,
        output_path=output_path,
        rotate_x=45,
    )


def plot_label_yearly_distribution(
    df: pd.DataFrame,
    title: str,
    output_path: Path,
) -> None:
    """
    Plot yearly distribution of a label.
    """

    if df.empty:
        return

    plot_bar(
        df,
        x_col="year",
        y_col="count",
        title=title,
        output_path=output_path,
    )


def plot_label_pipeline(
    df: pd.DataFrame,
    stack_cols: list[str],
    labels: list[str],
    title: str,
    output_path: Path,
) -> None:
    """
    Plot stacked pipeline chart.
    """

    if df.empty:
        return

    plot_stacked_bar(
        df,
        x_col="year",
        stack_cols=stack_cols,
        labels=labels,
        title=title,
        output_path=output_path,
    )

def plot_onboarding_by_repo(
    df: pd.DataFrame,
    title: str,
    output_path: Path,
) -> None:

    if df.empty:
        return

    plot_stacked_bar(
        df,
        x_col="repo",
        stack_cols=["gfic", "gfi"],
        labels=[
            "Good First Issue Candidate",
            "Good First Issue",
        ],
        title=title,
        output_path=output_path,
        rotate_x=45,
    )