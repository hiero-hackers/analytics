"""Tests for safe environment-variable parsing."""

from __future__ import annotations

from hiero_analytics.config.env import env_float, env_int


def test_env_int_reads_value(monkeypatch):
    """A valid integer env var is parsed."""
    monkeypatch.setenv("SOME_INT", "7")
    assert env_int("SOME_INT", 3) == 7


def test_env_int_falls_back_when_missing(monkeypatch):
    """A missing env var uses the default."""
    monkeypatch.delenv("SOME_INT", raising=False)
    assert env_int("SOME_INT", 3) == 3


def test_env_int_falls_back_on_invalid(monkeypatch):
    """Non-integer input falls back to the default instead of raising."""
    monkeypatch.setenv("SOME_INT", "not-a-number")
    assert env_int("SOME_INT", 3) == 3


def test_env_int_clamps_to_minimum(monkeypatch):
    """Values below the minimum are clamped (e.g. a zero worker count)."""
    monkeypatch.setenv("SOME_INT", "0")
    assert env_int("SOME_INT", 3, minimum=1) == 1


def test_env_float_reads_and_falls_back(monkeypatch):
    """Floats parse, and bad input falls back to the default."""
    monkeypatch.setenv("SOME_FLOAT", "1.5")
    assert env_float("SOME_FLOAT", 0.25) == 1.5
    monkeypatch.setenv("SOME_FLOAT", "")
    assert env_float("SOME_FLOAT", 0.25) == 0.25
