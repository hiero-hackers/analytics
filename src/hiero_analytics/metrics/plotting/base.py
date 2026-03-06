from __future__ import annotations

from pathlib import Path
import matplotlib.pyplot as plt

from hiero_analytics.config.charts import DEFAULT_DPI, DEFAULT_FIGSIZE
from .style import apply_style


def create_figure(figsize=DEFAULT_FIGSIZE):
    apply_style()
    return plt.figure(figsize=figsize)


def finalize_chart(
    title: str,
    xlabel: str,
    ylabel: str,
    output_path: Path,
    legend: bool = False,
    rotate_x: int | None = None,
) -> None:

    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)

    if rotate_x:
        plt.xticks(rotation=rotate_x)

    if legend:
        plt.legend()

    plt.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    plt.savefig(output_path, dpi=DEFAULT_DPI)
    plt.close()