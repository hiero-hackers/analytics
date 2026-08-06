"""Tests for the run_all pipeline orchestrator."""

import pytest

from hiero_analytics.pipelines import run_all


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


def test_run_pipelines_fail_fast_stops_after_first_failure():
    """With fail_fast, the first failure aborts the remaining pipelines."""
    calls = []

    def boom():
        calls.append("a")
        raise RuntimeError("kaboom")

    def ok_b():
        calls.append("b")

    failures = run_all.run_pipelines([("a", boom), ("b", ok_b)], fail_fast=True)

    assert calls == ["a"]
    assert failures == ["a"]


def test_run_extra_org_calls_runner_in_process_with_org(monkeypatch):
    """Extra orgs run the contributor-activity runner in-process, passing the org explicitly."""
    seen = []
    monkeypatch.setattr(run_all, "_resolve", lambda name: lambda org: seen.append((name, org)))

    assert run_all._run_extra_org("other-org") is True
    assert seen == [("contributor_activity", "other-org")]


def test_run_extra_org_reports_failure(monkeypatch):
    """A failing extra-org run returns False instead of raising."""

    def boom(org):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(run_all, "_resolve", lambda _name: boom)

    assert run_all._run_extra_org("other-org") is False


def test_run_pipelines_empty_when_all_succeed():
    """No failures are reported when every pipeline succeeds."""
    failures = run_all.run_pipelines([("a", lambda: None), ("b", lambda: None)])
    assert failures == []


def test_default_pipelines_come_from_registry():
    """The default run resolves every registry pipeline marked in_default_run."""
    names = [name for name, _ in run_all.default_pipelines()]

    assert "difficulty" in names
    assert "scorecard" in names
    # CLI-only pipelines stay out of the default run.
    assert "data_api" not in names
    assert "discord_analytics" not in names
    assert "contributor_churn" not in names


def test_pipeline_selection_uses_all_pipelines_online(monkeypatch):
    """Normal refresh runs retain every configured pipeline."""
    monkeypatch.delenv("HIERO_ANALYTICS_OFFLINE", raising=False)
    pipelines = [("difficulty", lambda: None), ("scorecard", lambda: None)]

    assert run_all.pipelines_for_current_mode(pipelines) == pipelines


def test_pipeline_selection_skips_network_only_pipelines_offline(monkeypatch):
    """Offline previews run durable dashboard producers and skip live-only work.

    ``difficulty`` is registered as offline-capable; ``scorecard`` is not.
    """
    monkeypatch.setenv("HIERO_ANALYTICS_OFFLINE", "1")

    def difficulty():
        return None

    def scorecard():
        return None

    assert run_all.pipelines_for_current_mode([("difficulty", difficulty), ("scorecard", scorecard)]) == [
        ("difficulty", difficulty)
    ]


def test_main_exits_nonzero_when_a_pipeline_fails(monkeypatch):
    """main() exits non-zero so CI surfaces any pipeline failure."""

    def boom():
        raise RuntimeError("fail")

    monkeypatch.setattr(run_all, "setup_logging", lambda: None)
    monkeypatch.setattr(run_all, "_resolve", lambda _name: lambda: None)
    monkeypatch.setattr(run_all, "default_pipelines", lambda: [("boom", boom)])
    monkeypatch.setattr(run_all, "EXTRA_ORGS", [])

    with pytest.raises(SystemExit) as exc_info:
        run_all.main()

    assert exc_info.value.code == 1


def test_main_fail_fast_skips_remaining_work_after_pipeline_failure(monkeypatch):
    """With fail_fast, main() exits after the first failure and skips later stages."""

    def boom():
        raise RuntimeError("fail")

    monkeypatch.setattr(run_all, "setup_logging", lambda: None)
    monkeypatch.setattr(run_all, "default_pipelines", lambda: [("boom", boom), ("later", lambda: None)])
    monkeypatch.setattr(run_all, "EXTRA_ORGS", ["extra-org"])

    extra_org_calls = []
    resolve_calls = []
    monkeypatch.setattr(run_all, "_run_extra_org", lambda org: extra_org_calls.append(org) or True)
    monkeypatch.setattr(run_all, "_resolve", lambda name: resolve_calls.append(name) or (lambda: None))

    with pytest.raises(SystemExit) as exc_info:
        run_all.main(fail_fast=True)

    assert exc_info.value.code == 1
    assert extra_org_calls == []
    assert resolve_calls == []


def test_main_succeeds_when_all_pipelines_pass(monkeypatch):
    """main() returns normally (no SystemExit) when all pipelines succeed."""
    monkeypatch.setattr(run_all, "setup_logging", lambda: None)
    monkeypatch.setattr(run_all, "_resolve", lambda _name: lambda: None)
    monkeypatch.setattr(run_all, "default_pipelines", lambda: [("ok", lambda: None)])
    monkeypatch.setattr(run_all, "EXTRA_ORGS", [])

    run_all.main()  # should not raise


def test_main_runs_extra_orgs_then_the_data_api_once(monkeypatch):
    """A failed extra org is reported; the data API still emits once, after all orgs."""
    monkeypatch.setattr(run_all, "setup_logging", lambda: None)
    monkeypatch.setattr(run_all, "default_pipelines", lambda: [("ok", lambda: None)])
    monkeypatch.setattr(run_all, "EXTRA_ORGS", ["good-org", "bad-org"])

    attempted = []
    monkeypatch.setattr(run_all, "_run_extra_org", lambda org: attempted.append(org) or org != "bad-org")
    renderer_runs = []
    monkeypatch.setattr(run_all, "_resolve", lambda name: lambda: renderer_runs.append(name))

    with pytest.raises(SystemExit):  # bad-org failed -> non-zero exit
        run_all.main()

    assert attempted == ["good-org", "bad-org"]  # every extra org attempted
    assert renderer_runs == ["data_api"]


def _prune_spy(monkeypatch) -> list[bool]:
    """Record whether main() reached the dataset prune."""
    calls: list[bool] = []
    monkeypatch.setattr(run_all, "prune_untouched_datasets", lambda: calls.append(True))
    monkeypatch.setattr(run_all, "setup_logging", lambda: None)
    monkeypatch.setattr(run_all, "_resolve", lambda _name: lambda: None)
    monkeypatch.setattr(run_all, "EXTRA_ORGS", [])
    return calls


def test_main_prunes_orphaned_datasets_after_a_clean_run(monkeypatch):
    """A complete online run is the only place an unclaimed dataset means "orphan"."""
    calls = _prune_spy(monkeypatch)
    monkeypatch.setattr(run_all, "default_pipelines", lambda: [("ok", lambda: None)])
    monkeypatch.setattr(run_all, "offline_mode_enabled", lambda: False)

    run_all.main()

    assert calls == [True]


def test_main_does_not_prune_when_a_pipeline_failed(monkeypatch):
    """A pipeline that failed may never have reached its fetch, so nothing is orphaned."""
    calls = _prune_spy(monkeypatch)

    def boom():
        raise RuntimeError("fail")

    monkeypatch.setattr(run_all, "default_pipelines", lambda: [("boom", boom)])
    monkeypatch.setattr(run_all, "offline_mode_enabled", lambda: False)

    with pytest.raises(SystemExit):
        run_all.main()

    assert calls == []


def test_main_does_not_prune_offline(monkeypatch):
    """Offline runs skip the network pipelines, so most datasets go unclaimed."""
    calls = _prune_spy(monkeypatch)
    monkeypatch.setattr(run_all, "default_pipelines", lambda: [("ok", lambda: None)])
    monkeypatch.setattr(run_all, "offline_mode_enabled", lambda: True)

    run_all.main()

    assert calls == []
