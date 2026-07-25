"""Tests that every saved figure carries its provenance stamp."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import pandas as pd
import pytest

from hiero_analytics.plotting import style
from hiero_analytics.plotting.bars import plot_bar
from hiero_analytics.plotting.base import create_figure, save_and_close
from hiero_analytics.plotting.style import draw_provenance_footer
from hiero_analytics.provenance import Provenance


@pytest.fixture
def known_provenance(monkeypatch):
    """Pin the stamp so assertions do not depend on the checkout or the datasets."""
    monkeypatch.setattr(
        style,
        "resolve_provenance",
        lambda *_args, **_kwargs: Provenance(
            data_as_of=pd.Timestamp("2026-07-25T09:14:00Z").to_pydatetime(),
            git_sha="abc1234",
        ),
    )


def _footer_texts(fig):
    """Figure-level texts, which is where the footer lives (axis texts excluded)."""
    return [text.get_text() for text in fig.texts]


def test_footer_carries_data_code_and_count(known_provenance):
    """A saved figure states which data, which revision, and how many rows drew it."""
    fig, _ = create_figure()

    draw_provenance_footer(fig, record_count=42)

    assert _footer_texts(fig) == ["data 2026-07-25 09:14 UTC · code abc1234 · n=42"]


def test_footer_is_omitted_when_nothing_resolves(monkeypatch):
    """No resolvable provenance draws no footer rather than an empty caption."""
    monkeypatch.setattr(
        style,
        "resolve_provenance",
        lambda *_args, **_kwargs: Provenance(data_as_of=None, git_sha=None),
    )
    fig, _ = create_figure()

    draw_provenance_footer(fig)

    assert _footer_texts(fig) == []


def test_footer_failure_never_breaks_a_render(monkeypatch, tmp_path):
    """A cosmetic stamp must not cost a chart, let alone a multi-hour run."""

    def _explode(*args, **kwargs):
        raise RuntimeError("provenance backend is down")

    monkeypatch.setattr(style, "resolve_provenance", _explode)
    fig, ax = create_figure()
    ax.plot([1, 2], [3, 4])
    output = tmp_path / "chart.png"

    save_and_close(fig, output, record_count=7)

    assert output.exists()


def test_saved_charts_are_stamped_through_the_public_api(known_provenance, tmp_path):
    """The count must reach the footer from a real chart call, not just directly."""
    captured: list[str] = []
    original = style.draw_provenance_footer

    def _spy(fig, *, record_count=None):
        captured.append(f"n={record_count}")
        return original(fig, record_count=record_count)

    # `base` imported the symbol directly, so patch it where it is looked up.
    from hiero_analytics.plotting import base

    base.draw_provenance_footer = _spy
    try:
        df = pd.DataFrame({"repo": ["a", "b", "c"], "count": [3, 2, 1]})
        plot_bar(df, x_col="repo", y_col="count", title="t", output_path=tmp_path / "bar.png")
    finally:
        base.draw_provenance_footer = original

    assert captured == ["n=3"]
    assert (tmp_path / "bar.png").exists()
