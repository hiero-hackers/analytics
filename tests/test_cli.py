"""Tests for the CLI and the pipeline registry that drives it."""

import inspect
from types import SimpleNamespace

import pytest

from hiero_analytics import cli
from hiero_analytics.pipelines import PIPELINES


def _fake_pipeline(entry, args=()):
    return SimpleNamespace(args=args, requires=frozenset(), resolve=lambda: entry)


def test_every_registered_pipeline_resolves_to_its_declared_signature():
    """Each registry entry imports, exposes main(), and accepts its declared options."""
    for pipeline in PIPELINES:
        entry = pipeline.resolve()
        params = inspect.signature(entry).parameters
        for option in pipeline.args:
            assert option in params, f"{pipeline.name} declares --{option} but main() does not accept it"


def test_unknown_command_exits_with_error():
    """Argparse rejects commands that are not in the registry."""
    with pytest.raises(SystemExit):
        cli.main(["not-a-pipeline"])


def test_cli_lists_registered_pipelines(capsys):
    """The list command prints registered pipeline names and returns success."""
    assert cli.main(["list"]) == 0

    output = capsys.readouterr().out
    assert "difficulty" in output
    assert "discord_analytics" in output
    assert "[CLI-only]" in output


def test_cli_runs_single_pipeline_and_forwards_options(monkeypatch):
    """A subcommand runs its pipeline, forwarding explicitly set options."""
    calls = []
    monkeypatch.setitem(cli.PIPELINES_BY_NAME, "scorecard", _fake_pipeline(lambda **kw: calls.append(kw), ("org",)))
    monkeypatch.setattr(cli, "setup_logging", lambda: None)

    assert cli.main(["scorecard", "--org", "my-org"]) == 0
    assert calls == [{"org": "my-org"}]


def test_cli_omits_unset_options_so_pipeline_defaults_apply(monkeypatch):
    """Options the user did not pass are omitted, so main()'s own defaults win."""
    calls = []
    monkeypatch.setitem(cli.PIPELINES_BY_NAME, "scorecard", _fake_pipeline(lambda **kw: calls.append(kw), ("org",)))
    monkeypatch.setattr(cli, "setup_logging", lambda: None)

    assert cli.main(["scorecard"]) == 0
    assert calls == [{}]


def test_cli_reports_pipeline_failure_with_exit_code(monkeypatch):
    """A pipeline that raises makes the CLI return a non-zero exit code."""

    def boom():
        raise RuntimeError("kaboom")

    monkeypatch.setitem(cli.PIPELINES_BY_NAME, "scorecard", _fake_pipeline(boom))
    monkeypatch.setattr(cli, "setup_logging", lambda: None)

    assert cli.main(["scorecard"]) == 1


def test_cli_defaults_to_full_run(monkeypatch):
    """No arguments (and the `all` command) run the full suite, lenient and continuing."""
    ran = []
    monkeypatch.setattr(cli.run_all, "main", lambda **kwargs: ran.append(kwargs))

    assert cli.main([]) == 0
    assert cli.main(["all"]) == 0
    assert ran == [{"fail_fast": False, "strict": False}] * 2


def test_cli_all_forwards_fail_fast_and_strict(monkeypatch):
    """The explicit `all` flags are forwarded to run_all.main()."""
    seen = []
    monkeypatch.setattr(cli.run_all, "main", lambda **kwargs: seen.append(kwargs))

    assert cli.main(["all", "--fail-fast"]) == 0
    assert cli.main(["all", "--strict"]) == 0
    assert seen == [{"fail_fast": True, "strict": False}, {"fail_fast": False, "strict": True}]


def test_cli_list_shows_capability_requirements(capsys):
    """`list` says which pipelines only run for orgs with a capability."""
    assert cli.main(["list"]) == 0

    lines = {line.split()[0]: line for line in capsys.readouterr().out.splitlines()}
    assert "[requires: governed]" in lines["role_coverage"]
    assert "[requires: hips]" in lines["hip_implementation"]
    assert "requires" not in lines["difficulty"]


def test_cli_single_pipeline_attributes_its_requests_to_the_org_and_pipeline(monkeypatch):
    """A one-pipeline run is attributed like a full run: (its --org, its name)."""
    from hiero_analytics.data_sources.usage import current_scope

    seen = []
    monkeypatch.setitem(
        cli.PIPELINES_BY_NAME, "scorecard", _fake_pipeline(lambda **_kw: seen.append(current_scope()), ("org",))
    )
    monkeypatch.setattr(cli, "setup_logging", lambda: None)

    assert cli.main(["scorecard", "--org", "my-org"]) == 0

    assert (seen[0].org, seen[0].dataset) == ("my-org", "scorecard")


def test_cli_single_pipeline_defaults_to_the_configured_org(monkeypatch):
    """Without --org the pipeline uses the configured org, and so does attribution."""
    from hiero_analytics.data_sources.usage import current_scope

    seen = []
    monkeypatch.setitem(
        cli.PIPELINES_BY_NAME, "scorecard", _fake_pipeline(lambda **_kw: seen.append(current_scope()), ("org",))
    )
    monkeypatch.setattr(cli, "setup_logging", lambda: None)

    cli.main(["scorecard"])

    assert seen[0].org == cli.ORG


def test_cli_single_pipeline_logs_its_usage_even_when_it_fails(monkeypatch, caplog):
    """A failed one-pipeline run still reports what it spent."""
    import logging

    def boom():
        raise RuntimeError("kaboom")

    monkeypatch.setitem(cli.PIPELINES_BY_NAME, "scorecard", _fake_pipeline(boom))
    monkeypatch.setattr(cli, "setup_logging", lambda: None)

    with caplog.at_level(logging.INFO, logger="hiero_analytics.cli"):
        assert cli.main(["scorecard"]) == 1

    assert any("GitHub API usage" in record.getMessage() for record in caplog.records)


def test_cli_warns_when_the_org_lacks_the_pipelines_capability(monkeypatch, caplog):
    """Running a governance pipeline for an ungoverned org is allowed, but flagged."""
    import logging

    monkeypatch.setitem(
        cli.PIPELINES_BY_NAME,
        "role_coverage",
        SimpleNamespace(args=("org",), requires=frozenset({"governed"}), resolve=lambda: lambda **_kw: None),
    )
    monkeypatch.setattr(cli, "setup_logging", lambda: None)

    with caplog.at_level(logging.WARNING, logger="hiero_analytics.cli"):
        assert cli.main(["role_coverage", "--org", "some-ungoverned-org"]) == 0

    assert any("governed" in record.getMessage() for record in caplog.records)
