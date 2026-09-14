"""Tests for the shared matplotlib style: typography registration and the title-free axes."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, findfont

from hiero_analytics.config.charts import FONT_FALLBACKS, FONT_FAMILY, FONT_WEIGHT_SEMIBOLD
from hiero_analytics.plotting.style import apply_style


def test_apply_style_resolves_the_bundled_font_family():
    """``FONT_FAMILY`` must resolve to a vendored face, not to the fallback.

    Without the explicit registration in ``apply_style`` matplotlib never looks
    at the repo's font directory, and every chart silently reverts to DejaVu
    Sans — the exact typeface mismatch with the web dashboard this replaces.
    """
    apply_style()

    resolved = Path(findfont(FontProperties(family=FONT_FAMILY)))

    assert resolved.name.startswith("Inter-")
    assert resolved.parent.name == "fonts"


def test_apply_style_resolves_semibold_to_its_own_face():
    """The value labels ask for semibold; it must map to SemiBold, not to faux-bolded Regular."""
    apply_style()

    regular = Path(findfont(FontProperties(family=FONT_FAMILY)))
    semibold = Path(findfont(FontProperties(family=FONT_FAMILY, weight=FONT_WEIGHT_SEMIBOLD)))

    assert semibold.name == "Inter-SemiBold.ttf"
    assert semibold != regular


def test_apply_style_sets_a_fallback_stack():
    """A font that fails to register must degrade to a face matplotlib always ships."""
    apply_style()

    assert plt.rcParams["font.family"] == ["sans-serif"]
    assert plt.rcParams["font.sans-serif"][0] == FONT_FAMILY
    assert plt.rcParams["font.sans-serif"][-1] == FONT_FALLBACKS[-1]
    assert Path(findfont(FontProperties(family=list(FONT_FALLBACKS)))).exists()


def test_apply_style_leaves_axes_titles_unstyled():
    """The style must not carry axes-title params it no longer has a title to draw.

    Charts export untitled and the dashboard captions them, so these stay at
    matplotlib's defaults; a re-appearing override is the tell that a title got
    styled back in.
    """
    apply_style()

    for param in ("axes.titlecolor", "axes.titleweight", "axes.titlepad", "axes.titlesize"):
        assert plt.rcParams[param] == matplotlib.rcParamsDefault[param], param
