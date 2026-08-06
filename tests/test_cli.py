"""Tests for the CLI and the pipeline registry that drives it."""

import inspect
from types import SimpleNamespace

import pytest

from hiero_analytics import cli
from hiero_analytics.pipelines import PIPELINES


def _fake_pipeline(entry, args=()):
    return SimpleNamespace(args=args, resolve=lambda: entry)


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
    """No arguments (and the `all` command) run the full suite."""
    ran = []
    monkeypatch.setattr(cli.run_all, "main", lambda fail_fast=False: ran.append(fail_fast))

    assert cli.main([]) == 0
    assert cli.main(["all"]) == 0
    assert ran == [False, False]


def test_cli_all_forwards_fail_fast(monkeypatch):
    """The explicit `all --fail-fast` flag is forwarded to run_all.main()."""
    seen = []
    monkeypatch.setattr(cli.run_all, "main", lambda fail_fast=False: seen.append(fail_fast))

    assert cli.main(["all", "--fail-fast"]) == 0
    assert seen == [True]
