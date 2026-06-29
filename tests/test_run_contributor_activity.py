"""Tests for the contributor-activity dashboard runner's dataset reuse."""

from __future__ import annotations

import hiero_analytics.run_contributor_activity_org as runner


def test_load_or_fetch_reuses_persisted_dataset(monkeypatch):
    """When a dataset exists on disk, its records are returned without fetching."""
    persisted = ["rec-a", "rec-b"]
    monkeypatch.setattr(
        runner, "load_dataset", lambda _path, _model: (persisted, "2024-01-01T00:00:00+00:00")
    )

    fetched = []

    def fetch_fn():
        fetched.append(True)
        return ["fresh"]

    result = runner._load_or_fetch("contributor_activity", object, fetch_fn)

    assert result == persisted
    assert fetched == []  # the network fetch was skipped


def test_load_or_fetch_falls_back_to_fetch_when_absent(monkeypatch):
    """With no persisted dataset, the runner fetches from GitHub."""
    monkeypatch.setattr(runner, "load_dataset", lambda _path, _model: None)

    result = runner._load_or_fetch("issue_label_events", object, lambda: ["fresh"])

    assert result == ["fresh"]
