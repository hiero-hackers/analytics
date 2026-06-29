"""Tests for the run_all pipeline orchestrator."""

import pytest

from hiero_analytics import run_all


def test_run_pipelines_runs_all_and_isolates_failures():
    """A failing pipeline is recorded but does not stop the others."""
    calls = []

    def ok_a():
        calls.append("a")

    def boom():
        calls.append("b")
        raise RuntimeError("kaboom")

    def ok_c():
        calls.append("c")

    failures = run_all.run_pipelines([("a", ok_a), ("b", boom), ("c", ok_c)])

    assert calls == ["a", "b", "c"]
    assert failures == ["b"]


def test_run_pipelines_empty_when_all_succeed():
    """No failures are reported when every pipeline succeeds."""
    failures = run_all.run_pipelines([("a", lambda: None), ("b", lambda: None)])
    assert failures == []


def test_main_exits_nonzero_when_a_pipeline_fails(monkeypatch):
    """main() exits non-zero so CI surfaces any pipeline failure."""

    def boom():
        raise RuntimeError("fail")

    monkeypatch.setattr(run_all, "setup_logging", lambda: None)
    monkeypatch.setattr(run_all, "PIPELINES", [("boom", boom)])

    with pytest.raises(SystemExit) as exc_info:
        run_all.main()

    assert exc_info.value.code == 1


def test_main_succeeds_when_all_pipelines_pass(monkeypatch):
    """main() returns normally (no SystemExit) when all pipelines succeed."""
    monkeypatch.setattr(run_all, "setup_logging", lambda: None)
    monkeypatch.setattr(run_all, "PIPELINES", [("ok", lambda: None)])

    run_all.main()  # should not raise
