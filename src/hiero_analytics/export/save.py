"""Utilities for saving DataFrames to CSV and rendering charts to disk."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


def write_output_meta(path: Path, *, generated_at: datetime | None = None) -> None:
    """Write the freshness sidecar (``<name>.meta.json``) for a saved artifact.

    The dashboard reads it to show a per-section "data as of" stamp — without
    it, a pipeline that fails after previously succeeding leaves yesterday's
    CSV rendering as current with no visible signal.
    """
    stamp = (generated_at or datetime.now(UTC)).isoformat()
    Path(f"{path}.meta.json").write_text(json.dumps({"generated_at": stamp}), encoding="utf-8")


def save_dataframe(
    df: pd.DataFrame,
    path: Path,
) -> None:
    """Write ``df`` to ``path`` as CSV, creating parent directories and the freshness sidecar."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    write_output_meta(path)


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
