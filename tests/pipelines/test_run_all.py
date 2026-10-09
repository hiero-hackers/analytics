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


def _fake_pipeline(name: str, runner, *, extra_orgs: bool = True, offline: bool = False):
    """A minimal stand-in for a registry Pipeline entry."""

    class _Fake:
        pass

    fake = _Fake()
    fake.name = name
    fake.extra_orgs = extra_orgs
    fake.offline = offline
    fake.resolve = lambda: runner
    return fake


def test_run_extra_org_runs_each_org_independent_pipeline(monkeypatch):
    """Extra orgs run every extra_orgs-flagged pipeline in-process, passing the org explicitly."""
    seen = []
    monkeypatch.setattr(
        run_all,
        "PIPELINES",
        (
            _fake_pipeline("difficulty", lambda org: seen.append(("difficulty", org))),
            _fake_pipeline("role_coverage", lambda org: seen.append(("role_coverage", org)), extra_orgs=False),
            _fake_pipeline("scorecard", lambda org: seen.append(("scorecard", org))),
        ),
    )

    assert run_all._run_extra_org("other-org") == []
    assert seen == [("difficulty", "other-org"), ("scorecard", "other-org")]


def test_run_extra_org_isolates_failures_per_pipeline(monkeypatch):
    """A failing extra-org pipeline is labelled name[org]; the rest still run."""

    def boom(org):
        raise RuntimeError("kaboom")

    seen = []
    monkeypatch.setattr(
        run_all,
        "PIPELINES",
        (
            _fake_pipeline("difficulty", boom),
            _fake_pipeline("scorecard", lambda org: seen.append(org)),
        ),
    )

    assert run_all._run_extra_org("other-org") == ["difficulty[other-org]"]
    assert seen == ["other-org"]


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
    monkeypatch.setattr(
        run_all,
        "_run_extra_org",
        lambda org: attempted.append(org) or ([] if org != "bad-org" else [f"difficulty[{org}]"]),
    )
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


# ---------------------------------------------------------
# API USAGE REPORTING (#525)
# ---------------------------------------------------------


def _usage_client(monkeypatch):
    """A real client on a faked session, installed as the process-wide shared client."""
    from unittest.mock import Mock

    from hiero_analytics.data_sources.github_client import GitHubClient
    from hiero_analytics.pipelines import _shared

    response = Mock()
    response.status_code = 200
    response.ok = True
    response.headers = {}
    response.json.return_value = {}
    client = GitHubClient()
    monkeypatch.setattr(client.session, "request", Mock(return_value=response))
    monkeypatch.setattr(_shared, "_client", client)
    return client


def _usage_main_env(monkeypatch, tmp_path, pipelines):
    """Stub everything main() touches except usage, with the manifest in a sandbox."""
    datasets = tmp_path / "usage_datasets"
    datasets.mkdir()
    monkeypatch.setattr(run_all, "DATASETS_DIR", datasets)
    monkeypatch.setattr(run_all, "setup_logging", lambda: None)
    monkeypatch.setattr(run_all, "_resolve", lambda _name: lambda: None)
    monkeypatch.setattr(run_all, "default_pipelines", lambda: pipelines)
    monkeypatch.setattr(run_all, "EXTRA_ORGS", [])
    monkeypatch.setattr(run_all, "ORG", "primary-org")
    return datasets / run_all.SNAPSHOT_MANIFEST_NAME


def _manifest(path):
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def test_run_pipelines_attributes_each_pipeline_to_the_primary_org():
    """A pipeline's own requests are scoped to (primary org, pipeline name)."""
    from hiero_analytics.data_sources.usage import current_scope

    seen = []
    run_all.run_pipelines([("alpha", lambda: seen.append(current_scope()))])

    assert seen[0].dataset == "alpha"
    assert seen[0].org == run_all.ORG
    assert current_scope().org is None  # the scope does not leak out


def test_run_extra_org_attributes_requests_to_that_org(monkeypatch):
    """Extra-org pipelines run under (extra org, pipeline name)."""
    from hiero_analytics.data_sources.usage import current_scope

    seen = []
    monkeypatch.setattr(run_all, "PIPELINES", [_fake_pipeline("diff", lambda **_kwargs: seen.append(current_scope()))])
    monkeypatch.setattr(run_all, "offline_mode_enabled", lambda: False)

    run_all._run_extra_org("extra-org")

    assert (seen[0].org, seen[0].dataset) == ("extra-org", "diff")


def test_main_records_api_usage_in_the_manifest(monkeypatch, tmp_path):
    """The run's per-org spend is archived in SNAPSHOT.json."""
    client = _usage_client(monkeypatch)
    manifest_path = _usage_main_env(monkeypatch, tmp_path, [("p", lambda: client.get("https://api.github.com/x"))])

    run_all.main()

    usage = _manifest(manifest_path)["api_usage"]
    assert usage["total"]["rest_requests"] == 1
    assert usage["orgs"]["primary-org"]["datasets"]["p"]["rest_requests"] == 1


def test_main_reports_only_its_own_runs_spend(monkeypatch, tmp_path):
    """Usage recorded before main() starts must not leak into the run's report."""
    client = _usage_client(monkeypatch)
    client.get("https://api.github.com/earlier")  # e.g. a previous run in the same process
    manifest_path = _usage_main_env(monkeypatch, tmp_path, [("p", lambda: None)])

    run_all.main()

    assert _manifest(manifest_path)["api_usage"]["total"]["rest_requests"] == 0


def test_main_reports_zero_usage_when_no_client_was_needed(monkeypatch, tmp_path):
    """An offline-style run that never built a client reports zeros, without building one."""
    from hiero_analytics.pipelines import _shared

    monkeypatch.setattr(_shared, "_client", None)
    manifest_path = _usage_main_env(monkeypatch, tmp_path, [("p", lambda: None)])

    run_all.main()

    assert _manifest(manifest_path)["api_usage"] == {
        "total": {"rest_requests": 0, "graphql_requests": 0, "graphql_points": 0},
        "graphql_remaining": None,
        "orgs": {},
    }
    assert _shared._client is None


def test_main_reports_spend_even_when_a_pipeline_fails(monkeypatch, tmp_path):
    """A partial run still reports what it spent before it failed."""
    client = _usage_client(monkeypatch)

    def spends_then_fails():
        client.get("https://api.github.com/x")
        raise RuntimeError("kaboom")

    manifest_path = _usage_main_env(monkeypatch, tmp_path, [("p", spends_then_fails)])
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    with pytest.raises(SystemExit):
        run_all.main()

    manifest = _manifest(manifest_path)
    assert manifest["failed_pipelines"] == ["p"]
    assert manifest["api_usage"]["total"]["rest_requests"] == 1
    assert "## GitHub API usage" in summary.read_text(encoding="utf-8")


def test_job_summary_renders_the_same_figures_as_the_manifest(monkeypatch, tmp_path):
    """The Actions job summary is rendered from the manifest's own api_usage block."""
    from hiero_analytics.data_sources.usage import render_usage_markdown

    client = _usage_client(monkeypatch)
    manifest_path = _usage_main_env(monkeypatch, tmp_path, [("p", lambda: client.get("https://api.github.com/x"))])
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    run_all.main()

    assert render_usage_markdown(_manifest(manifest_path)["api_usage"]) in summary.read_text(encoding="utf-8")


def test_job_summary_appends_rather_than_overwrites(monkeypatch, tmp_path):
    """Other steps write to the same summary file; ours must not clobber them."""
    summary = tmp_path / "summary.md"
    summary.write_text("earlier step\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    run_all._write_usage_step_summary(
        {
            "total": {"rest_requests": 0, "graphql_requests": 0, "graphql_points": 0},
            "graphql_remaining": None,
            "orgs": {},
        }
    )

    text = summary.read_text(encoding="utf-8")
    assert text.startswith("earlier step\n")
    assert "No GitHub API requests were made" in text


def test_job_summary_is_skipped_outside_actions(monkeypatch, tmp_path):
    """No GITHUB_STEP_SUMMARY, no file written, no error."""
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    run_all._write_usage_step_summary({"total": {}, "orgs": {}})

    assert list(cwd.iterdir()) == []


def test_unwritable_job_summary_does_not_fail_the_run(monkeypatch, tmp_path):
    """A summary is a convenience; failing to write it must not fail the run."""
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path))  # a directory: opening it raises OSError

    run_all._write_usage_step_summary(
        {
            "total": {"rest_requests": 0, "graphql_requests": 0, "graphql_points": 0},
            "graphql_remaining": None,
            "orgs": {},
        }
    )


def test_fail_fast_still_reports_spend_in_the_job_summary(monkeypatch, tmp_path):
    """fail_fast skips the manifest, but the budget it spent is still reported."""
    client = _usage_client(monkeypatch)

    def spends_then_fails():
        client.get("https://api.github.com/x")
        raise RuntimeError("kaboom")

    manifest_path = _usage_main_env(monkeypatch, tmp_path, [("p", spends_then_fails)])
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    with pytest.raises(SystemExit):
        run_all.main(fail_fast=True)

    assert not manifest_path.exists()
    assert "primary-org" in summary.read_text(encoding="utf-8")
