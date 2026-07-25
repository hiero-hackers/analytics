"""Utilities for saving DataFrames to CSV and rendering charts to disk."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from hiero_analytics.provenance import git_sha


def write_output_meta(
    path: Path,
    *,
    generated_at: datetime | None = None,
    record_count: int | None = None,
) -> None:
    """Write the provenance sidecar (``<name>.meta.json``) for a saved artifact.

    The dashboard reads ``generated_at`` to show a per-section "data as of"
    stamp — without it, a pipeline that fails after previously succeeding leaves
    yesterday's CSV rendering as current with no visible signal.

    ``git_sha`` and ``record_count`` complete the picture for anyone reading the
    CSV directly rather than through the dashboard: the revision that wrote it,
    and the row count that distinguishes a genuine decline from a truncated
    fetch. The CSV body is deliberately left unstamped — these files are read
    back with ``pd.read_csv`` (by the dashboard among others), so a comment
    preamble would break the pipeline to serve a reader who has the sidecar.
    """
    stamp = (generated_at or datetime.now(UTC)).isoformat()
    meta: dict[str, object] = {"generated_at": stamp, "git_sha": git_sha()}
    if record_count is not None:
        meta["record_count"] = record_count
    Path(f"{path}.meta.json").write_text(json.dumps(meta), encoding="utf-8")


def save_dataframe(
    df: pd.DataFrame,
    path: Path,
) -> None:
    """Write ``df`` to ``path`` as CSV, creating parent directories and the provenance sidecar."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    write_output_meta(path, record_count=len(df))


def plot_and_save(
    df: pd.DataFrame,
    plot_fn: Callable[..., None],
    *,
    output_path: Path,
    csv_path: Path | None = None,
    **plot_kwargs: object,
) -> None:
    """
    Render a chart and optionally save its source data, skipping empty frames.

    Collapses the ``if not df.empty: plot_x(...); save_dataframe(...)`` block
    repeated across runners. ``df`` is passed positionally so any chart helper
    works regardless of its first parameter's name (``df``/``channels``/...).
    Extra keyword arguments are forwarded to ``plot_fn``; if ``csv_path`` is
    given the frame is also written there as CSV. Empty frames are skipped.
    """
    if df.empty:
        return

    plot_fn(df, output_path=output_path, **plot_kwargs)

    if csv_path is not None:
        save_dataframe(df, csv_path)
