"""Tests for the run_all orchestrator: one loop over every rendered org.

Pipelines here are stand-ins with the registry's shape (name, args, offline,
requires) and the org registry is a synthetic one, so the tests pin the
scheduling rules rather than today's roster: a pipeline runs for an org when
the org's profile has every capability the pipeline requires.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from hiero_analytics.config import orgs, paths
from hiero_analytics.config.orgs import OrgProfile
from hiero_analytics.data_sources.usage import current_scope
from hiero_analytics.pipelines import run_all

PRIMARY = "primary-org"
GOVERNED = "governed-org"
PLAIN = "plain-org"


def _pipeline(name, runner=None, *, requires=(), offline=False, args=("org",)):
    """A registry-shaped stand-in; ``runner`` receives the org as a keyword."""
    entry = runner or (lambda **_kwargs: None)
    return SimpleNamespace(
        name=name,
        args=args,
        offline=offline,
        requires=frozenset(requires),
        repo_scoped="repo" in args,
        resolve=lambda: entry,
    )


@pytest.fixture
def registry(monkeypatch):
    """A synthetic registry: a governed primary, a governed extra and a plain extra."""
    monkeypatch.setattr(
        orgs,
        "ORGS",
        (
            OrgProfile(name=PRIMARY, governed=True, governance_url="https://example.test/p.yaml"),
            OrgProfile(name=GOVERNED, governed=True, governance_url="https://example.test/g.yaml", extra=True),
            OrgProfile(name=PLAIN, org_overview=True, extra=True),
        ),
    )
    monkeypatch.setenv("GITHUB_ORG", PRIMARY)
    monkeypatch.setattr(paths, "ORG", PRIMARY)


@pytest.fixture
def main_env(monkeypatch, registry):
    """Stub everything main() touches except scheduling; returns the manifest path."""
    monkeypatch.setattr(run_all, "setup_logging", lambda: None)
    monkeypatch.setattr(run_all, "_resolve", lambda _name: lambda: None)
    monkeypatch.setattr(run_all, "prune_untouched_datasets", lambda **_kwargs: None)
    monkeypatch.setattr(run_all, "offline_mode_enabled", lambda: False)
    return paths.DATASETS_DIR / run_all.SNAPSHOT_MANIFEST_NAME


def _use(monkeypatch, *pipelines):
    """Make these stand-ins the default run."""
    monkeypatch.setattr(run_all, "default_run_pipelines", lambda: list(pipelines))


def _manifest(path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------
# SCHEDULING
# ---------------------------------------------------------


def test_pipelines_follow_each_orgs_capabilities(monkeypatch, registry):
    """Governance pipelines run for governed orgs, overview for overview orgs, plain ones everywhere."""
    monkeypatch.setattr(run_all, "offline_mode_enabled", lambda: False)
    _use(
        monkeypatch,
        _pipeline("difficulty"),
        _pipeline("role_coverage", requires={"governed"}),
        _pipeline("org_overview", requires={"org_overview"}),
        _pipeline("hip_implementation", requires={"hips"}),
    )

    def names(org, primary=False):
        return [pipeline.name for pipeline in run_all.pipelines_for(org, primary=primary)]

    assert names(PRIMARY, primary=True) == ["difficulty", "role_coverage"]
    assert names(GOVERNED) == ["difficulty", "role_coverage"]
    assert names(PLAIN) == ["difficulty", "org_overview"]
    # An unregistered (trial) org has no capabilities.
    assert names("trial-org") == ["difficulty"]


def test_repo_scoped_pipelines_run_for_the_primary_org_only(monkeypatch, registry):
    """GITHUB_REPO belongs to the primary org, so repo-scoped pipelines never run elsewhere."""
    monkeypatch.setattr(run_all, "offline_mode_enabled", lambda: False)
    _use(monkeypatch, _pipeline("onboarding", args=("org", "repo")), _pipeline("difficulty"))

    assert [p.name for p in run_all.pipelines_for(PRIMARY, primary=True)] == ["onboarding", "difficulty"]
    assert [p.name for p in run_all.pipelines_for(PLAIN, primary=False)] == ["difficulty"]


def test_offline_runs_keep_only_offline_capable_pipelines(monkeypatch, registry):
    """Offline previews skip network-only pipelines for every org."""
    monkeypatch.setattr(run_all, "offline_mode_enabled", lambda: True)
    _use(monkeypatch, _pipeline("difficulty", offline=True), _pipeline("scorecard"))

    assert [p.name for p in run_all.pipelines_for(PRIMARY, primary=True)] == ["difficulty"]


def test_the_real_registry_runs_governance_only_where_governed():
    """The shipped registry: governance and HIPs pipelines need the capability, the rest do not."""
    from hiero_analytics.pipelines import PIPELINES_BY_NAME

    for name in ("maintainer_pipeline", "role_coverage", "affiliation"):
        assert PIPELINES_BY_NAME[name].requires == {"governed"}, name
    assert PIPELINES_BY_NAME["hip_implementation"].requires == {"hips"}
    assert PIPELINES_BY_NAME["org_overview"].requires == {"org_overview"}
    for name in ("difficulty", "contributor_activity", "contributor_heatmap", "releases", "ci_health"):
        assert PIPELINES_BY_NAME[name].requires == frozenset(), name


# ---------------------------------------------------------
# RUNNING ONE ORG
# ---------------------------------------------------------


def test_run_org_passes_the_org_and_isolates_failures(monkeypatch, registry):
    """Each pipeline receives the org explicitly; a failure is recorded and the rest still run."""
    monkeypatch.setattr(run_all, "offline_mode_enabled", lambda: False)
    seen = []

    def boom(**_kwargs):
        raise RuntimeError("kaboom")

    _use(
        monkeypatch,
        _pipeline("a", lambda **kwargs: seen.append(("a", kwargs))),
        _pipeline("b", boom),
        _pipeline("c", lambda **kwargs: seen.append(("c", kwargs))),
    )

    assert run_all.run_org(PLAIN, primary=False) == ["b[plain-org]"]
    assert seen == [("a", {"org": PLAIN}), ("c", {"org": PLAIN})]
    # Primary-org failures keep their bare names, as SNAPSHOT.json always recorded them.
    assert run_all.run_org(PRIMARY, primary=True) == ["b"]


def test_run_org_fail_fast_stops_at_the_first_failure(monkeypatch, registry):
    """With fail_fast, nothing after the first failure runs."""
    monkeypatch.setattr(run_all, "offline_mode_enabled", lambda: False)
    calls = []

    def boom(**_kwargs):
        calls.append("a")
        raise RuntimeError("kaboom")

    _use(monkeypatch, _pipeline("a", boom), _pipeline("b", lambda **_k: calls.append("b")))

    assert run_all.run_org(PRIMARY, primary=True, fail_fast=True) == ["a"]
    assert calls == ["a"]


def test_run_org_attributes_requests_to_the_org_and_pipeline(monkeypatch, registry):
    """Each pipeline runs under the (org, pipeline) usage scope, and the scope does not leak."""
    monkeypatch.setattr(run_all, "offline_mode_enabled", lambda: False)
    seen = []
    _use(monkeypatch, _pipeline("diff", lambda **_k: seen.append(current_scope())))

    run_all.run_org(GOVERNED, primary=False)

    assert (seen[0].org, seen[0].dataset) == (GOVERNED, "diff")
    assert current_scope().org is None


def test_run_org_skips_an_extra_org_with_no_cached_datasets_offline(monkeypatch, registry):
    """An org registered since the base branch's cache was saved is skipped, not failed, offline."""
    monkeypatch.setattr(run_all, "offline_mode_enabled", lambda: True)
    calls = []
    _use(monkeypatch, _pipeline("difficulty", lambda **kwargs: calls.append(kwargs["org"]), offline=True))

    assert run_all.run_org(PLAIN, primary=False) == []
    assert calls == []

    (paths.DATASETS_DIR / f"issues_{PLAIN}_all.json").write_text("{}", encoding="utf-8")
    assert run_all.run_org(PLAIN, primary=False) == []
    assert calls == [PLAIN]


def test_run_org_skips_an_org_that_fails_the_preflight(monkeypatch, registry):
    """A misspelt or missing org is reported once and fetches nothing."""
    monkeypatch.setattr(run_all, "offline_mode_enabled", lambda: False)
    monkeypatch.setattr(run_all, "preflight_org", lambda org: f"{org} is spelt differently")
    calls = []
    _use(monkeypatch, _pipeline("difficulty", lambda **kwargs: calls.append(kwargs)))

    assert run_all.run_org(PLAIN, primary=False) == ["preflight[plain-org]"]
    assert run_all.run_org(PRIMARY, primary=True) == ["preflight"]
    assert calls == []


# ---------------------------------------------------------
# PREFLIGHT
# ---------------------------------------------------------


@pytest.mark.parametrize(
    ("github_says", "problem"),
    [
        ("plain-org", None),
        ("Plain-Org", "spelt 'Plain-Org' on GitHub"),
        (None, "does not exist on GitHub"),
    ],
)
def test_preflight_checks_the_exact_spelling(monkeypatch, github_says, problem):
    """A login must exist and match GitHub's casing, since paths and joins are case-sensitive."""
    monkeypatch.setattr(run_all, "offline_mode_enabled", lambda: False)
    monkeypatch.setattr(run_all, "fetch_org_login", lambda _client, _org: github_says)

    result = run_all.preflight_org(PLAIN)

    assert result is None if problem is None else problem in result


def test_preflight_lets_an_org_run_when_the_lookup_itself_fails(monkeypatch, caplog):
    """A transport failure is not evidence about the org: warn, and run it anyway."""
    import logging

    monkeypatch.setattr(run_all, "offline_mode_enabled", lambda: False)

    def down(_client, _org):
        raise ConnectionError("network down")

    monkeypatch.setattr(run_all, "fetch_org_login", down)

    with caplog.at_level(logging.WARNING, logger=run_all.logger.name):
        assert run_all.preflight_org(PLAIN) is None

    assert any("network down" in record.getMessage() for record in caplog.records)


def test_preflight_is_skipped_offline(monkeypatch):
    """Offline previews make no GitHub calls at all."""
    monkeypatch.setattr(run_all, "offline_mode_enabled", lambda: True)
    monkeypatch.setattr(run_all, "fetch_org_login", Mock(side_effect=AssertionError("called")))

    assert run_all.preflight_org(PLAIN) is None


def test_fetch_org_login_reads_the_canonical_login():
    """The lookup returns GitHub's spelling, or None for a missing org in either error shape."""
    from hiero_analytics.data_sources.github_ingest import fetch_org_login

    client = Mock()
    client.graphql.return_value = {"data": {"organization": {"login": "LFDT-CLPR"}}}
    assert fetch_org_login(client, "lfdt-clpr") == "LFDT-CLPR"

    client.graphql.return_value = {"data": {"organization": None}}
    assert fetch_org_login(client, "ghost") is None

    client.graphql.side_effect = RuntimeError("GitHub GraphQL error: {'errors': [{'type': 'NOT_FOUND'}]}")
    assert fetch_org_login(client, "ghost") is None

    client.graphql.side_effect = RuntimeError("GitHub GraphQL error: something else")
    with pytest.raises(RuntimeError):
        fetch_org_login(client, "ghost")


# ---------------------------------------------------------
# THE FULL RUN
# ---------------------------------------------------------


def test_main_renders_every_org_then_the_data_api_once(monkeypatch, main_env):
    """Primary first, then extras, each with its own pipelines; the data API runs last, once."""
    order = []
    _use(
        monkeypatch,
        _pipeline("difficulty", lambda **kwargs: order.append(("difficulty", kwargs["org"]))),
        _pipeline(
            "role_coverage", lambda **kwargs: order.append(("role_coverage", kwargs["org"])), requires={"governed"}
        ),
    )
    monkeypatch.setattr(run_all, "_resolve", lambda name: lambda: order.append((name, None)))

    run_all.main()

    assert order == [
        ("difficulty", PRIMARY),
        ("role_coverage", PRIMARY),
        ("difficulty", GOVERNED),
        ("role_coverage", GOVERNED),
        ("difficulty", PLAIN),
        ("data_api", None),
    ]


def test_main_exits_nonzero_when_a_primary_pipeline_fails(monkeypatch, main_env):
    """A primary-org failure fails the run, so the scheduled deploy keeps the last good site."""

    def boom(**kwargs):
        if kwargs["org"] == PRIMARY:
            raise RuntimeError("fail")

    _use(monkeypatch, _pipeline("p", boom))

    with pytest.raises(SystemExit) as exc_info:
        run_all.main()

    assert exc_info.value.code == 1
    assert _manifest(main_env)["failed_pipelines"] == ["p"]


def test_main_tolerates_a_failure_confined_to_an_extra_org(monkeypatch, main_env, tmp_path, capsys):
    """An extra org's failure is recorded and reported, and the run still succeeds and publishes."""

    def boom(**kwargs):
        if kwargs["org"] == PLAIN:
            raise RuntimeError("fail")

    _use(monkeypatch, _pipeline("p", boom))
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    emitted = []
    monkeypatch.setattr(run_all, "_resolve", lambda name: lambda: emitted.append(name))

    run_all.main()  # no SystemExit

    assert _manifest(main_env)["failed_pipelines"] == ["p[plain-org]"]
    assert emitted == ["data_api"]
    text = summary.read_text(encoding="utf-8")
    assert "## Pipeline failures" in text and "`p[plain-org]`" in text
    assert "still published" in text
    assert "::warning title=Analytics pipelines::" in capsys.readouterr().out


def test_main_strict_fails_on_any_org(monkeypatch, main_env):
    """--strict (PR previews) treats an extra org's failure like any other."""

    def boom(**kwargs):
        if kwargs["org"] == GOVERNED:
            raise RuntimeError("fail")

    _use(monkeypatch, _pipeline("p", boom))

    with pytest.raises(SystemExit):
        run_all.main(strict=True)


def test_main_fails_when_the_data_api_fails_even_if_orgs_succeeded(monkeypatch, main_env):
    """The data API is the published surface; its failure always blocks."""
    _use(monkeypatch, _pipeline("p"))

    def broken():
        raise RuntimeError("contract")

    monkeypatch.setattr(run_all, "_resolve", lambda _name: broken)

    with pytest.raises(SystemExit):
        run_all.main()


def test_main_fail_fast_skips_later_orgs_and_the_data_api(monkeypatch, main_env):
    """fail_fast stops at the first failure anywhere and skips the remaining work."""
    seen = []

    def boom(**kwargs):
        seen.append(kwargs["org"])
        if kwargs["org"] == GOVERNED:
            raise RuntimeError("fail")

    _use(monkeypatch, _pipeline("p", boom))
    emitted = []
    monkeypatch.setattr(run_all, "_resolve", lambda name: lambda: emitted.append(name))

    with pytest.raises(SystemExit):
        run_all.main(fail_fast=True)

    assert seen == [PRIMARY, GOVERNED]
    assert emitted == []
    assert not main_env.exists()


def test_main_succeeds_when_all_pipelines_pass(monkeypatch, main_env):
    """main() returns normally (no SystemExit) when everything succeeds."""
    _use(monkeypatch, _pipeline("ok"))

    run_all.main()

    assert _manifest(main_env)["failed_pipelines"] == []


# ---------------------------------------------------------
# DATASET PRUNE
# ---------------------------------------------------------


def _prune_spy(monkeypatch) -> list[bool]:
    """Record whether main() reached the dataset prune."""
    calls: list[bool] = []
    monkeypatch.setattr(run_all, "prune_untouched_datasets", lambda **_kwargs: calls.append(True))
    return calls


def test_main_prunes_orphaned_datasets_after_a_clean_run(monkeypatch, main_env):
    """A complete online run is the only place an unclaimed dataset means "orphan"."""
    calls = _prune_spy(monkeypatch)
    _use(monkeypatch, _pipeline("ok"))

    run_all.main()

    assert calls == [True]


def test_main_does_not_prune_when_the_primary_org_failed(monkeypatch, main_env):
    """A failed primary pipeline may never have reached its fetch, so nothing is judged orphaned."""
    calls = _prune_spy(monkeypatch)

    def boom(**kwargs):
        if kwargs["org"] == PRIMARY:
            raise RuntimeError("fail")

    _use(monkeypatch, _pipeline("p", boom))

    with pytest.raises(SystemExit):
        run_all.main()

    assert calls == []


def test_main_does_not_prune_offline(monkeypatch, main_env):
    """Offline runs skip the network pipelines, so most datasets go unclaimed."""
    calls = _prune_spy(monkeypatch)
    monkeypatch.setattr(run_all, "offline_mode_enabled", lambda: True)
    _use(monkeypatch, _pipeline("ok", offline=True))

    run_all.main()

    assert calls == []


# ---------------------------------------------------------
# API USAGE REPORTING (#525)
# ---------------------------------------------------------


def _usage_client(monkeypatch):
    """A real client on a faked session, installed as the process-wide shared client."""
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


def test_main_records_api_usage_per_org_in_the_manifest(monkeypatch, main_env):
    """The run's spend is archived in SNAPSHOT.json, split by the org each request served."""
    client = _usage_client(monkeypatch)
    _use(monkeypatch, _pipeline("p", lambda **_k: client.get("https://api.github.com/x")))
    monkeypatch.setenv("GITHUB_EXTRA_ORGS", PLAIN)

    run_all.main()

    usage = _manifest(main_env)["api_usage"]
    assert usage["total"]["rest_requests"] == 2
    assert usage["orgs"][PRIMARY]["datasets"]["p"]["rest_requests"] == 1
    assert usage["orgs"][PLAIN]["datasets"]["p"]["rest_requests"] == 1


def test_main_reports_only_its_own_runs_spend(monkeypatch, main_env):
    """Usage recorded before main() starts must not leak into the run's report."""
    client = _usage_client(monkeypatch)
    client.get("https://api.github.com/earlier")  # e.g. a previous run in the same process
    _use(monkeypatch, _pipeline("p"))

    run_all.main()

    assert _manifest(main_env)["api_usage"]["total"]["rest_requests"] == 0


def test_main_reports_zero_usage_when_no_client_was_needed(monkeypatch, main_env):
    """An offline-style run that never built a client reports zeros, without building one."""
    from hiero_analytics.pipelines import _shared

    monkeypatch.setattr(_shared, "_client", None)
    _use(monkeypatch, _pipeline("p"))

    run_all.main()

    assert _manifest(main_env)["api_usage"] == {
        "total": {"rest_requests": 0, "graphql_requests": 0, "graphql_points": 0},
        "graphql_remaining": None,
        "orgs": {},
    }
    assert _shared._client is None


def test_main_reports_spend_even_when_a_pipeline_fails(monkeypatch, main_env, tmp_path):
    """A partial run still reports what it spent before it failed."""
    client = _usage_client(monkeypatch)

    def spends_then_fails(**kwargs):
        client.get("https://api.github.com/x")
        if kwargs["org"] == PRIMARY:
            raise RuntimeError("kaboom")

    monkeypatch.setenv("GITHUB_EXTRA_ORGS", "")
    _use(monkeypatch, _pipeline("p", spends_then_fails))
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    with pytest.raises(SystemExit):
        run_all.main()

    manifest = _manifest(main_env)
    assert manifest["failed_pipelines"] == ["p"]
    assert manifest["api_usage"]["total"]["rest_requests"] == 1
    assert "## GitHub API usage" in summary.read_text(encoding="utf-8")


def test_job_summary_renders_the_same_figures_as_the_manifest(monkeypatch, main_env, tmp_path):
    """The Actions job summary is rendered from the manifest's own api_usage block."""
    from hiero_analytics.data_sources.usage import render_usage_markdown

    client = _usage_client(monkeypatch)
    _use(monkeypatch, _pipeline("p", lambda **_k: client.get("https://api.github.com/x")))
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    run_all.main()

    assert render_usage_markdown(_manifest(main_env)["api_usage"]) in summary.read_text(encoding="utf-8")


def test_fail_fast_still_reports_spend_in_the_job_summary(monkeypatch, main_env, tmp_path):
    """fail_fast skips the manifest, but the budget it spent is still reported."""
    client = _usage_client(monkeypatch)

    def spends_then_fails(**_kwargs):
        client.get("https://api.github.com/x")
        raise RuntimeError("kaboom")

    _use(monkeypatch, _pipeline("p", spends_then_fails))
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    with pytest.raises(SystemExit):
        run_all.main(fail_fast=True)

    assert not main_env.exists()
    assert PRIMARY in summary.read_text(encoding="utf-8")


# ---------------------------------------------------------
# JOB SUMMARY
# ---------------------------------------------------------

_ZERO_USAGE = {
    "total": {"rest_requests": 0, "graphql_requests": 0, "graphql_points": 0},
    "graphql_remaining": None,
    "orgs": {},
}


def test_job_summary_appends_rather_than_overwrites(monkeypatch, tmp_path):
    """Other steps write to the same summary file; ours must not clobber them."""
    summary = tmp_path / "summary.md"
    summary.write_text("earlier step\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    run_all._write_usage_step_summary(_ZERO_USAGE)

    text = summary.read_text(encoding="utf-8")
    assert text.startswith("earlier step\n")
    assert "No GitHub API requests were made" in text


def test_job_summary_is_skipped_outside_actions(monkeypatch, tmp_path):
    """No GITHUB_STEP_SUMMARY, no file written, no error."""
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    run_all._write_usage_step_summary(_ZERO_USAGE)

    assert list(cwd.iterdir()) == []


def test_unwritable_job_summary_does_not_fail_the_run(monkeypatch, tmp_path):
    """A summary is a convenience; failing to write it must not fail the run."""
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path))  # a directory: opening it raises OSError

    run_all._write_usage_step_summary(_ZERO_USAGE)


def test_failures_section_says_whether_the_run_published():
    """The failure list names each label, and says when the run still published."""
    assert run_all.render_failures_markdown([], tolerated=True) == ""
    tolerated = run_all.render_failures_markdown(["p[plain-org]"], tolerated=True)
    blocking = run_all.render_failures_markdown(["p"], tolerated=False)
    assert "`p[plain-org]`" in tolerated and "still published" in tolerated
    assert "`p`" in blocking and "still published" not in blocking


def test_failure_labels_distinguish_extra_orgs():
    """Only ``name[org]`` labels belong to extra or trial orgs."""
    assert run_all.is_org_scoped_failure("difficulty[plain-org]")
    assert not run_all.is_org_scoped_failure("difficulty")
    assert not run_all.is_org_scoped_failure("data_api")


def test_failures_section_explains_a_skipped_org():
    """A preflight failure means the whole org is absent, and the summary says so."""
    text = run_all.render_failures_markdown(["preflight[plain-org]"], tolerated=True)
    assert "skipped entirely" in text


def test_failed_orgs_are_read_from_the_labels():
    """Only ``name[org]`` labels name an org; bare labels belong to the primary org or the run."""
    assert run_all.failed_orgs(["p[plain-org]", "preflight[governed-org]", "p", "data_api"]) == {
        PLAIN,
        GOVERNED,
    }


def test_main_prunes_but_keeps_a_failed_extra_orgs_datasets(monkeypatch, main_env):
    """Tolerated failures still prune orphans, but never the failing org's own datasets."""
    seen = []
    monkeypatch.setattr(run_all, "prune_untouched_datasets", lambda keep: seen.append(keep))

    def boom(**kwargs):
        if kwargs["org"] == PLAIN:
            raise RuntimeError("fail")

    _use(monkeypatch, _pipeline("p", boom))

    run_all.main()

    (keep,) = seen
    assert keep(paths.DATASETS_DIR / f"issues_{PLAIN}_all.json")
    assert not keep(paths.DATASETS_DIR / f"issues_{GOVERNED}_all.json")
    assert not keep(paths.DATASETS_DIR / "issues_old-trial-org_all.json")


@pytest.mark.parametrize(
    ("narrow", "rendered", "kept", "judged"),
    [
        pytest.param({"GITHUB_EXTRA_ORGS": GOVERNED}, [PRIMARY, GOVERNED], [PLAIN], [PRIMARY, GOVERNED], id="extras"),
        pytest.param(
            {"GITHUB_ORG": PLAIN, "GITHUB_EXTRA_ORGS": ""}, [PLAIN], [PRIMARY, GOVERNED], [PLAIN], id="primary"
        ),
    ],
)
def test_main_keeps_datasets_of_registered_orgs_the_environment_left_out(
    monkeypatch, main_env, caplog, narrow, rendered, kept, judged
):
    """A narrowed run prunes only what it could judge: registered-but-unrendered orgs keep their cache."""
    for name, value in narrow.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(run_all, "_rendered_orgs", lambda: list(rendered))
    seen = []
    monkeypatch.setattr(run_all, "prune_untouched_datasets", lambda keep: seen.append(keep))
    _use(monkeypatch, _pipeline("p"))

    with caplog.at_level("INFO", logger="hiero_analytics.pipelines.run_all"):
        run_all.main()

    (keep,) = seen
    for org in kept:
        assert keep(paths.DATASETS_DIR / f"issues_{org}_all.json"), org
    for org in judged:
        assert not keep(paths.DATASETS_DIR / f"issues_{org}_all.json"), org
    assert not keep(paths.DATASETS_DIR / "issues_old-trial-org_all.json")
    left_out = [r for r in caplog.records if "leaves out registered org" in r.getMessage()]
    assert len(left_out) == 1
    assert all(org in left_out[0].getMessage() for org in kept)


def test_main_is_silent_about_left_out_orgs_when_the_registry_is_rendered(monkeypatch, main_env, caplog):
    """The full registry run has nothing to disclose."""
    _use(monkeypatch, _pipeline("p"))
    with caplog.at_level("INFO", logger="hiero_analytics.pipelines.run_all"):
        run_all.main()
    assert not [r for r in caplog.records if "leaves out registered org" in r.getMessage()]
