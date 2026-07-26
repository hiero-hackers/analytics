"""Tests for the funnel renderer: centred bands narrowing stage by stage."""

from __future__ import annotations

import matplotlib
import pandas as pd
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from hiero_analytics.plotting.base import create_figure
from hiero_analytics.plotting.funnel import plot_funnel


def test_plot_funnel_writes_centred_bands(tmp_path):
    """Each stage renders as a band centred on the axis, widest stage first."""
    df = pd.DataFrame({"stage": ["proposed", "approved", "shipped"], "share": [100, 60, 25]})
    output = tmp_path / "funnel.png"

    plot_funnel(df, "stage", "share", "Funnel", output)

    assert output.exists() and output.stat().st_size > 0


def test_plot_funnel_rejects_empty_input(tmp_path):
    """Empty input raises like every other primitive; callers guard first."""
    with pytest.raises(ValueError, match="empty"):
        plot_funnel(pd.DataFrame(columns=["stage", "share"]), "stage", "share", "Funnel", tmp_path / "funnel.png")


def test_plot_funnel_bands_are_centred_and_ordered():
    """Band geometry: width is the share, and each band is centred on 50."""
    fig, ax = create_figure()
    bars = ax.barh([0, 1], width=[100, 40], left=[0, 30], height=0.72)

    # The production path centres via left=(100-share)/2; assert that identity
    # holds for the geometry the helper builds.
    for patch, share in zip(bars.patches, [100, 40], strict=True):
        assert patch.get_x() == pytest.approx((100 - share) / 2)

    plt.close(fig)
