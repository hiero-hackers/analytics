"""Tests for the adaptive concurrency limiter (deterministic AIMD logic)."""

from __future__ import annotations

from hiero_analytics.data_sources.adaptive_limiter import _GROW_AFTER, AdaptiveConcurrencyLimiter


def test_starts_at_max_with_no_in_flight():
    """A fresh limiter sits at its max cap with nothing in flight."""
    lim = AdaptiveConcurrencyLimiter(8)
    assert lim.limit == 8
    assert lim.in_flight == 0


def test_throttle_halves_down_to_floor():
    """Each throttle halves the cap, never below the floor."""
    lim = AdaptiveConcurrencyLimiter(8, min_concurrency=1)
    lim.on_throttle()
    assert lim.limit == 4
    lim.on_throttle()
    assert lim.limit == 2
    lim.on_throttle()
    assert lim.limit == 1
    lim.on_throttle()
    assert lim.limit == 1  # floored at min


def test_success_recovers_after_a_streak():
    """The cap nudges up by one only after a streak of clean responses."""
    lim = AdaptiveConcurrencyLimiter(4)
    lim.on_throttle()  # -> 2
    assert lim.limit == 2
    for _ in range(_GROW_AFTER - 1):
        lim.on_success()
    assert lim.limit == 2  # not yet
    lim.on_success()
    assert lim.limit == 3  # one step up


def test_success_at_max_never_exceeds_max():
    """Successes at the cap don't grow it past max."""
    lim = AdaptiveConcurrencyLimiter(2)
    for _ in range(_GROW_AFTER * 2):
        lim.on_success()
    assert lim.limit == 2


def test_slot_tracks_in_flight_and_releases():
    """Entering a slot raises in-flight; leaving restores it (even nested)."""
    lim = AdaptiveConcurrencyLimiter(2)
    with lim.slot():
        assert lim.in_flight == 1
        with lim.slot():
            assert lim.in_flight == 2
    assert lim.in_flight == 0


def test_min_cannot_exceed_max():
    """A min above max is clamped down to max."""
    lim = AdaptiveConcurrencyLimiter(1, min_concurrency=5)
    assert lim.limit == 1
    lim.on_throttle()
    assert lim.limit == 1
