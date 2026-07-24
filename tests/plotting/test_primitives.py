"""Tests for the pure plotting primitives (palette, value formatting, axis-type check)."""

from __future__ import annotations

import pandas as pd

from hiero_analytics.plotting.primitives import build_palette, format_chart_value, is_numeric_or_datetime


def test_build_palette_cycles_when_more_colours_are_requested_than_exist():
    """A palette request larger than the base wraps around instead of running short."""
    palette = build_palette(5, palette=["#a", "#b"])
    assert palette == ["#a", "#b", "#a", "#b", "#a"]


def test_format_chart_value_drops_noisy_decimals_and_adds_thousands_separators():
    """Integers render without decimals; non-integers keep one decimal place."""
    assert format_chart_value(1200) == "1,200"
    assert format_chart_value(1200.0) == "1,200"  # integral float -> no decimal
    assert format_chart_value(3.14) == "3.1"


def test_is_numeric_or_datetime_distinguishes_quantitative_axes():
    """Numeric, datetime, and period series are quantitative; plain strings are not."""
    assert is_numeric_or_datetime(pd.Series([1, 2, 3])) is True
    assert is_numeric_or_datetime(pd.Series(pd.to_datetime(["2024-01-01", "2024-02-01"]))) is True
    assert is_numeric_or_datetime(pd.Series(["a", "b"])) is False
