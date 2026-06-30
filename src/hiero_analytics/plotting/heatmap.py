"""Heatmap chart renderer: a labelled, colour-coded grid with optional cell values."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Normalize

from hiero_analytics.config.charts import ACTIVITY_HEATMAP_CMAP, ACTIVITY_HEATMAP_PALETTE


def plot_heatmap(
    values: np.ndarray,
    *,
    row_labels: list[str],
    col_labels: list[str],
    output_path: Path,
    title: str,
    xlabel: str,
    ylabel: str,
    value_label: str,
    cmap: str = ACTIVITY_HEATMAP_CMAP,
    palette: dict[str, str] | None = None,
    annotate: bool = True,
) -> None:
    """Render a ``rows × cols`` heatmap (cells coloured by intensity) to a PNG.

    ``values`` is a 2-D array aligned to ``row_labels`` / ``col_labels``; cells are
    normalized 0..max and coloured with ``cmap``. With ``annotate`` each cell shows
    its integer value. No-ops on an empty matrix.
    """
    palette = palette or ACTIVITY_HEATMAP_PALETTE
    matrix = np.asarray(values, dtype=float)
    if matrix.size == 0:
        return

    normalization = Normalize(vmin=0, vmax=max(float(matrix.max()), 1.0))
    cmap_obj = plt.get_cmap(cmap)

    width = max(10.0, len(col_labels) * 1.15 + 4.0)
    height = max(6.0, len(row_labels) * 0.4 + 2.4)
    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_facecolor(palette["figure_bg"])
    ax.set_facecolor(palette["axes_bg"])
    ax.grid(False)  # the project style enables a grid globally; it must not overlay the heatmap

    image = ax.imshow(matrix, aspect="auto", cmap=cmap_obj, norm=normalization, interpolation="nearest")

    ax.set_xticks(range(len(col_labels)))
    ax.set_xticklabels(col_labels, rotation=45, ha="right")
    ax.set_yticks(range(len(row_labels)))
    ax.set_yticklabels(list(row_labels))

    if annotate:
        for row_index, row_values in enumerate(matrix):
            for column_index, cell_value in enumerate(row_values):
                text_color = palette["text_dark"] if normalization(cell_value) < 0.6 else palette["text_light"]
                ax.text(
                    column_index,
                    row_index,
                    int(cell_value),
                    ha="center",
                    va="center",
                    fontsize=9,
                    fontweight="semibold",
                    color=text_color,
                )

    ax.set_title(title, loc="left", color=palette["text_dark"])
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.tick_params(axis="both", colors=palette["tick"])
    colorbar = fig.colorbar(image, ax=ax, pad=0.02)
    colorbar.set_label(value_label)

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
