"""Tests for the aliased multi-repo batched GraphQL engine."""

from unittest.mock import Mock

import pytest

from hiero_analytics.data_sources.dataset_store import PartialOrgFetchError
from hiero_analytics.data_sources.github_client import GitHubServerError
from hiero_analytics.data_sources.github_ingest import batched
from hiero_analytics.data_sources.models import ReleaseRecord, RepositoryRecord
from hiero_analytics.data_sources.pagination import PageSizePolicy
from hiero_analytics.data_sources.queries import load_query
from hiero_analytics.data_sources.rate_limit import GraphQLResponseError

_QUERY = """query TEST_QUERY($owner:String!,$repo:String!,$cursor:String,$pageSize:Int!,$states:[IssueState!]){
  repository(owner:$owner,name:$repo){
    issues(first:$pageSize, after:$cursor, states:$states){
      pageInfo{ hasNextPage endCursor }
      nodes{ id }
    }
  }
  rateLimit{ limit remaining cost resetAt }
}
fragment F on Issue { id }"""


class _FakeModel:
    """Hydrates (repo, node id) tuples so tests can trace record provenance."""

    @classmethod
    def from_github_node(cls, node, context):
        return [(context["repo"], node["id"])]


def _repo(name: str) -> RepositoryRecord:
    return RepositoryRecord(full_name=f"org/{name}", name=name, owner="org")


def _page(ids, *, has_next=False, cursor=None):
    return {
        "issues": {
            "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
            "nodes": [{"id": i} for i in ids],
        }
    }


# ---------------------------------------------------------
# query splitting / assembly
# ---------------------------------------------------------


def test_split_repo_query_extracts_shared_vars_body_and_fragments():
    """Per-repo variables drop out; the repository body and fragments are preserved."""
    shared, body, fragments = batched.split_repo_query(_QUERY)

    assert shared == ["$pageSize:Int!", "$states:[IssueState!]"]
    assert "issues(first:$pageSize" in body
    assert "repository" not in body
    assert "rateLimit" not in body
    assert fragments.startswith("fragment F on Issue")


@pytest.mark.parametrize("query_name", ["issues", "issues_since", "issue_label_events", "merged_pr"])
def test_split_repo_query_handles_every_batched_production_query(query_name):
    """Each production query wired into the batched engine parses cleanly."""
    shared, body, fragments = batched.split_repo_query(load_query(query_name))

    assert all(decl.split(":", 1)[0].strip("$ ") not in {"owner", "repo", "cursor"} for decl in shared)
    assert "pageInfo" in body
    if query_name != "merged_pr":
        assert "fragment" in fragments


def test_build_round_query_aliases_repos_with_own_cursors():
    """Each repo gets an alias and its own cursor variable; shared vars stay declared once."""
    shared, body, fragments = batched.split_repo_query(_QUERY)

    query = batched._build_round_query(shared, body, fragments, [(0, _repo("a")), (2, _repo("b"))])

    assert 'r0: repository(owner: "org", name: "a")' in query
    assert 'r2: repository(owner: "org", name: "b")' in query
    assert "$c0: String" in query and "$c2: String" in query
    assert "after:$c0" in query and "after:$c2" in query
    assert query.count("$states:[IssueState!]") == 1
    assert "fragment F on Issue" in query


# ---------------------------------------------------------
# paging
# ---------------------------------------------------------


def test_batched_fetch_pages_repos_independently():
    """Repos page at their own depth; completed repos drop out of later rounds."""
    client = Mock()
    client.graphql.side_effect = [
        {"data": {"r0": _page([1, 2], has_next=True, cursor="CUR"), "r1": _page([10])}},
        {"data": {"r0": _page([3])}},
    ]

    records, failed = batched.fetch_repos_batched(
        client,
        [_repo("a"), _repo("b")],
        _QUERY,
        _FakeModel,
        ["issues"],
        lambda repo: {"repo": repo.full_name},
    )

    assert failed == []
    assert sorted(records) == [("org/a", 1), ("org/a", 2), ("org/a", 3), ("org/b", 10)]
    assert client.graphql.call_count == 2
    second_query, second_vars = client.graphql.call_args_list[1][0]
    assert "r0:" in second_query and "r1:" not in second_query  # b completed in round 1
    assert second_vars["c0"] == "CUR"


def test_batched_fetch_stop_node_ends_pagination_early():
    """A matching stop node ends that repo's pagination even with pages remaining."""
    client = Mock()
    client.graphql.side_effect = [
        {"data": {"r0": _page(["new", "old"], has_next=True, cursor="CUR")}},
    ]

    records, failed = batched.fetch_repos_batched(
        client,
        [_repo("a")],
        _QUERY,
        _FakeModel,
        ["issues"],
        lambda repo: {"repo": repo.full_name},
        stop_node=lambda node: node["id"] == "old",
    )

    assert failed == []
    assert client.graphql.call_count == 1  # no second round despite hasNextPage
    assert [r[1] for r in records] == ["new", "old"]  # boundary node still returned


def test_batched_fetch_missing_alias_joins_per_repo_fallback():
    """A null repository alias is retried per-repo, never silently treated as complete."""
    client = Mock()
    client.graphql.side_effect = [
        {"data": {"r0": _page([1]), "r1": None}},
    ]

    records, failed = batched.fetch_repos_batched(
        client,
        [_repo("a"), _repo("gone")],
        _QUERY,
        _FakeModel,
        ["issues"],
        lambda repo: {"repo": repo.full_name},
    )

    assert [r.name for r in failed] == ["gone"]
    assert records == [("org/a", 1)]


def test_batched_fetch_repeating_cursor_fails_the_repo_instead_of_looping():
    """A non-advancing cursor drops that page, resumes once from the last good cursor, then fails the repo."""
    client = Mock()
    client.graphql.side_effect = [
        {"data": {"r0": _page([1], has_next=True, cursor="SAME")}},
        {"data": {"r0": _page([2], has_next=True, cursor="SAME")}},  # cursor did not advance
        {"data": {"r0": _page([2], has_next=True, cursor="SAME")}},  # nor on the resume
    ]

    records, failed = batched.fetch_repos_batched(
        client,
        [_repo("a")],
        _QUERY,
        _FakeModel,
        ["issues"],
        lambda repo: {"repo": repo.full_name},
    )

    assert client.graphql.call_count == 3  # terminated, no spin
    assert [call[0][1]["c0"] for call in client.graphql.call_args_list] == [None, "SAME", "SAME"]
    assert [r.name for r in failed] == ["a"]
    # The caller retries a failed repo from scratch, so its partial pages are not returned.
    assert records == []


def test_batched_fetch_transient_stall_heals_on_the_resume():
    """A one-off stall costs one request: the resume re-sends the last good cursor and the repo completes."""
    client = Mock()
    client.graphql.side_effect = [
        {"data": {"r0": _page([1], has_next=True, cursor="C1")}},
        {"data": {"r0": _page([2], has_next=True, cursor=None)}},  # hasNextPage without a cursor
        {"data": {"r0": _page([2])}},
    ]

    records, failed = batched.fetch_repos_batched(
        client, [_repo("a")], _QUERY, _FakeModel, ["issues"], lambda repo: {"repo": repo.full_name}
    )

    assert failed == []
    assert records == [("org/a", 1), ("org/a", 2)]  # the stalled page was not kept twice
    assert [call[0][1]["c0"] for call in client.graphql.call_args_list] == [None, "C1", "C1"]


def test_batched_fetch_null_end_cursor_is_a_stall_not_completion():
    """HasNextPage with a null endCursor used to end the repo as if complete; now it fails it."""
    client = Mock()
    client.graphql.return_value = {"data": {"r0": _page([1], has_next=True, cursor=None)}}

    records, failed = batched.fetch_repos_batched(
        client, [_repo("a")], _QUERY, _FakeModel, ["issues"], lambda repo: {"repo": repo.full_name}
    )

    assert records == []
    assert [r.name for r in failed] == ["a"]
    assert client.graphql.call_count == 1  # no page fetched, so nothing to resume: straight to the fallback


def test_batched_fetch_cycling_cursor_is_caught():
    """A cursor that cycles back to one already sent (A, B, A) is a stall, not just an immediate repeat."""
    client = Mock()
    client.graphql.side_effect = [
        {"data": {"r0": _page([1], has_next=True, cursor="A")}},
        {"data": {"r0": _page([2], has_next=True, cursor="B")}},
        {"data": {"r0": _page([3], has_next=True, cursor="A")}},
        {"data": {"r0": _page([3], has_next=True, cursor="A")}},
    ]

    records, failed = batched.fetch_repos_batched(
        client, [_repo("a")], _QUERY, _FakeModel, ["issues"], lambda repo: {"repo": repo.full_name}
    )

    assert [r.name for r in failed] == ["a"]
    assert records == []
    assert client.graphql.call_count == 4


def test_batched_fetch_page_cap_fails_the_repo_without_a_resume(monkeypatch):
    """A connection that keeps advancing past GITHUB_GRAPHQL_MAX_PAGES fails instead of running on."""
    monkeypatch.setattr(batched, "GITHUB_GRAPHQL_MAX_PAGES", 2)
    client = Mock()
    client.graphql.side_effect = [{"data": {"r0": _page([i], has_next=True, cursor=f"C{i}")}} for i in range(10)]

    records, failed = batched.fetch_repos_batched(
        client, [_repo("a")], _QUERY, _FakeModel, ["issues"], lambda repo: {"repo": repo.full_name}
    )

    assert [r.name for r in failed] == ["a"]
    assert records == []
    assert client.graphql.call_count == 2  # a resume would only run past the cap again


def test_batched_fetch_refills_a_freed_slot_from_the_queue():
    """Repos wait in a queue; when one completes, the next joins the following round."""
    client = Mock()
    client.graphql.side_effect = [
        {"data": {"r0": _page([1]), "r1": _page([10], has_next=True, cursor="B1")}},
        {"data": {"r1": _page([11]), "r2": _page([20])}},
    ]

    records, failed = batched.fetch_repos_batched(
        client,
        [_repo("a"), _repo("b"), _repo("c")],
        _QUERY,
        _FakeModel,
        ["issues"],
        lambda repo: {"repo": repo.full_name},
        batch_size=2,
    )

    assert failed == []
    assert records == [("org/a", 1), ("org/b", 10), ("org/b", 11), ("org/c", 20)]
    second_query, second_vars = client.graphql.call_args_list[1][0]
    assert "r0:" not in second_query and "r1:" in second_query and "r2:" in second_query
    assert second_vars["c1"] == "B1" and second_vars["c2"] is None


# ---------------------------------------------------------
# adaptive round page size
# ---------------------------------------------------------


def test_build_round_query_declares_page_size_once_as_a_shared_variable():
    """$pageSize is a shared declaration, so every alias in the round uses the same value."""
    shared, body, fragments = batched.split_repo_query(_QUERY)

    query = batched._build_round_query(shared, body, fragments, [(0, _repo("a")), (1, _repo("b"))])

    assert query.count("$pageSize:Int!") == 1
    assert query.count("first:$pageSize") == 2


def test_batched_round_sends_the_configured_page_size():
    """Every round carries the default page size in its variables."""
    client = Mock()
    client.graphql.return_value = {"data": {"r0": _page([1])}}

    batched.fetch_repos_batched(
        client, [_repo("a")], _QUERY, _FakeModel, ["issues"], lambda repo: {"repo": repo.full_name}
    )

    assert client.graphql.call_args[0][1]["pageSize"] == PageSizePolicy().current


def test_batched_round_shrinks_on_server_error_and_keeps_alias_cursors():
    """A 5xx halves the round's page size for all aliases while each keeps its own cursor."""
    client = Mock()
    client.graphql.side_effect = [
        {"data": {"r0": _page([1], has_next=True, cursor="CA"), "r1": _page([10], has_next=True, cursor="CB")}},
        GitHubServerError("502"),
        {"data": {"r0": _page([2]), "r1": _page([11])}},
    ]

    records, failed = batched.fetch_repos_batched(
        client,
        [_repo("a"), _repo("b")],
        _QUERY,
        _FakeModel,
        ["issues"],
        lambda repo: {"repo": repo.full_name},
    )

    assert failed == []
    assert sorted(records) == [("org/a", 1), ("org/a", 2), ("org/b", 10), ("org/b", 11)]
    sent = [call[0][1] for call in client.graphql.call_args_list]
    assert [v["pageSize"] for v in sent] == [100, 100, 50]
    assert sent[1]["c0"] == sent[2]["c0"] == "CA"
    assert sent[1]["c1"] == sent[2]["c1"] == "CB"


def test_batched_round_reduced_size_persists_and_recovers():
    """The reduced round size persists for later rounds and doubles back after three clean rounds."""
    client = Mock()
    client.graphql.side_effect = [
        GitHubServerError("502"),
        {"data": {"r0": _page([1], has_next=True, cursor="C1")}},
        {"data": {"r0": _page([2], has_next=True, cursor="C2")}},
        {"data": {"r0": _page([3], has_next=True, cursor="C3")}},
        {"data": {"r0": _page([4])}},
    ]

    batched.fetch_repos_batched(
        client, [_repo("a")], _QUERY, _FakeModel, ["issues"], lambda repo: {"repo": repo.full_name}
    )

    sizes = [call[0][1]["pageSize"] for call in client.graphql.call_args_list]
    assert sizes == [100, 50, 50, 50, 100]


def _page_floor_25(monkeypatch):
    """Make the round page size start at 100 with a floor of 25 (the width policy is unaffected)."""
    monkeypatch.setattr(
        batched,
        "PageSizePolicy",
        lambda page_size=100, min_page_size=25, **kwargs: PageSizePolicy(page_size, min_page_size, **kwargs),
    )


def test_batched_round_at_the_floor_reraises_into_the_per_repo_fallback(monkeypatch):
    """A server error that survives shrinking page size and width to their floors fails each repo."""
    _page_floor_25(monkeypatch)
    client = Mock()
    client.graphql.side_effect = GitHubServerError("502")

    records, failed = batched.fetch_repos_batched(
        client, [_repo("a"), _repo("b")], _QUERY, _FakeModel, ["issues"], lambda repo: {"repo": repo.full_name}
    )

    assert records == []
    assert [r.name for r in failed] == ["a", "b"]
    sent = [call[0] for call in client.graphql.call_args_list]
    assert [variables["pageSize"] for _query, variables in sent] == [100, 50, 25, 25]
    # Width shrank 5 -> 2 -> 1, so the last two rounds carry one repo each.
    assert ["r1:" in query for query, _variables in sent] == [True, True, False, True]


# ---------------------------------------------------------
# GraphQL errors in the response body (recorded shapes)
# ---------------------------------------------------------


def _resource_limits(path):
    """A RESOURCE_LIMITS_EXCEEDED error object, as GitHub returns it alongside partial data."""
    return {
        "type": "RESOURCE_LIMITS_EXCEEDED",
        "path": path,
        "locations": [{"line": 8, "column": 5}],
        "message": "Resource limits for this query exceeded.",
    }


def test_resource_limit_error_keeps_clean_aliases_and_retries_the_affected_one_smaller():
    """Aliases without an error advance; the one that ran over retries from its cursor at a smaller size."""
    client = Mock()
    client.graphql.side_effect = [
        GraphQLResponseError(
            {
                "data": {"r0": _page([1], has_next=True, cursor="A1"), "r1": None, "r2": _page([20])},
                "errors": [_resource_limits(["r1", "issues"])],
            }
        ),
        {"data": {"r1": _page([10]), "r0": _page([2])}},
    ]

    records, failed = batched.fetch_repos_batched(
        client,
        [_repo("a"), _repo("b"), _repo("c")],
        _QUERY,
        _FakeModel,
        ["issues"],
        lambda repo: {"repo": repo.full_name},
    )

    assert failed == []
    assert records == [("org/a", 1), ("org/a", 2), ("org/b", 10), ("org/c", 20)]
    second_query, second_vars = client.graphql.call_args_list[1][0]
    assert second_vars["pageSize"] == 50
    assert second_vars["c1"] is None  # b retries the page it never got
    assert second_vars["c0"] == "A1"  # a moved on
    assert "r2:" not in second_query  # c completed in the failing round and was kept


def test_resource_limit_on_a_later_page_resumes_from_the_last_good_cursor():
    """A resource error on page 3 re-sends page 3's cursor; pages 1 and 2 are neither lost nor duplicated."""
    client = Mock()
    client.graphql.side_effect = [
        {"data": {"r0": _page([1], has_next=True, cursor="C1")}},
        {"data": {"r0": _page([2], has_next=True, cursor="C2")}},
        GraphQLResponseError({"data": {"r0": None}, "errors": [_resource_limits(["r0", "issues"])]}),
        {"data": {"r0": _page([3])}},
    ]

    records, failed = batched.fetch_repos_batched(
        client, [_repo("a")], _QUERY, _FakeModel, ["issues"], lambda repo: {"repo": repo.full_name}
    )

    assert failed == []
    assert records == [("org/a", 1), ("org/a", 2), ("org/a", 3)]
    sent = [call[0][1] for call in client.graphql.call_args_list]
    assert [(v["c0"], v["pageSize"]) for v in sent] == [(None, 100), ("C1", 100), ("C2", 100), ("C2", 50)]


def test_max_node_limit_without_a_path_shrinks_the_whole_round():
    """An error with no alias path (the query was rejected before running) retries every alias smaller."""
    client = Mock()
    client.graphql.side_effect = [
        GraphQLResponseError(
            {
                "errors": [
                    {
                        "type": "MAX_NODE_LIMIT_EXCEEDED",
                        "message": "This query requests up to 1,000,000 possible nodes "
                        "which exceeds the maximum limit of 500,000.",
                    }
                ]
            }
        ),
        {"data": {"r0": _page([1]), "r1": _page([10])}},
    ]

    records, failed = batched.fetch_repos_batched(
        client, [_repo("a"), _repo("b")], _QUERY, _FakeModel, ["issues"], lambda repo: {"repo": repo.full_name}
    )

    assert failed == []
    assert sorted(records) == [("org/a", 1), ("org/b", 10)]
    assert [call[0][1]["pageSize"] for call in client.graphql.call_args_list] == [100, 50]


def test_a_resource_error_at_both_floors_fails_only_the_affected_repo(monkeypatch):
    """When nothing is left to shrink, the repo that keeps running over fails; its neighbours complete."""
    _page_floor_25(monkeypatch)
    over = {"data": {"r1": None}, "errors": [_resource_limits(["r1", "issues"])]}
    client = Mock()
    client.graphql.side_effect = [
        GraphQLResponseError({**over, "data": {"r0": _page([1], has_next=True, cursor="A1"), "r1": None}}),
        GraphQLResponseError({**over, "data": {"r1": None, "r0": _page([2], has_next=True, cursor="A2")}}),
        GraphQLResponseError(over),  # width 1, page 25: both floors
        {"data": {"r0": _page([3])}},
    ]

    records, failed = batched.fetch_repos_batched(
        client, [_repo("a"), _repo("b")], _QUERY, _FakeModel, ["issues"], lambda repo: {"repo": repo.full_name}
    )

    assert [r.name for r in failed] == ["b"]
    assert records == [("org/a", 1), ("org/a", 2), ("org/a", 3)]


def test_a_non_resource_error_fails_only_that_alias_without_shrinking():
    """NOT_FOUND on one alias fails that repo alone; the round's other aliases advance at full size."""
    client = Mock()
    client.graphql.side_effect = [
        GraphQLResponseError(
            {
                "data": {"r0": _page([1], has_next=True, cursor="A1"), "r1": None},
                "errors": [
                    {
                        "type": "NOT_FOUND",
                        "path": ["r1"],
                        "message": "Could not resolve to a Repository with the name 'org/gone'.",
                    }
                ],
            }
        ),
        {"data": {"r0": _page([2])}},
    ]

    records, failed = batched.fetch_repos_batched(
        client, [_repo("a"), _repo("gone")], _QUERY, _FakeModel, ["issues"], lambda repo: {"repo": repo.full_name}
    )

    assert [r.name for r in failed] == ["gone"]
    assert records == [("org/a", 1), ("org/a", 2)]
    assert [call[0][1]["pageSize"] for call in client.graphql.call_args_list] == [100, 100]


# ---------------------------------------------------------
# failure handling
# ---------------------------------------------------------


def test_batched_fetch_failed_chunk_reports_repos_not_raises():
    """A failing batch marks its repos as failed instead of raising."""
    client = Mock()
    client.graphql.side_effect = RuntimeError("boom")

    records, failed = batched.fetch_repos_batched(
        client,
        [_repo("a"), _repo("b")],
        _QUERY,
        _FakeModel,
        ["issues"],
        lambda repo: {"repo": repo.full_name},
        batch_size=2,
    )

    assert records == []
    assert [r.name for r in failed] == ["a", "b"]


def test_batched_fetch_refuses_unsafe_repo_names():
    """A repo name that can't be safely inlined goes to the per-repo path instead."""
    weird = RepositoryRecord(full_name='org/we"ird', name='we"ird', owner="org")
    client = Mock()
    client.graphql.return_value = {"data": {"r0": _page([1])}}

    records, failed = batched.fetch_repos_batched(
        client,
        [_repo("a"), weird],
        _QUERY,
        _FakeModel,
        ["issues"],
        lambda repo: {"repo": repo.full_name},
    )

    assert records == [("org/a", 1)]
    assert failed == [weird]


def _not_found(alias):
    return {"type": "NOT_FOUND", "path": [alias], "message": "Could not resolve to a Repository."}


def _fetch_org(client, per_repo):
    return batched.fetch_org_records_batched(
        client,
        "org",
        query_text=_QUERY,
        model_class=_FakeModel,
        nodes_path=["issues"],
        per_repo=per_repo,
        task_desc="test records",
        max_workers=2,
    )


def test_org_batched_falls_back_per_repo_and_composes_partial(monkeypatch):
    """Untouched repos retry per-repo; a repo that failed partway keeps its pages and skips the restart."""
    done, flaky, broken, partway = _repo("done"), _repo("flaky"), _repo("broken"), _repo("partway")
    monkeypatch.setattr(batched._common, "fetch_org_repos_graphql", lambda *_a, **_k: [done, flaky, broken, partway])
    client = Mock()
    client.graphql.side_effect = [
        GraphQLResponseError(
            {
                "data": {"r0": _page([1]), "r1": None, "r2": None, "r3": _page([30], has_next=True, cursor="P1")},
                "errors": [_not_found("r1"), _not_found("r2")],
            }
        ),
        GraphQLResponseError({"data": {"r3": None}, "errors": [_not_found("r3")]}),
        GraphQLResponseError({"data": {"r3": None}, "errors": [_not_found("r3")]}),  # the resume fails too
    ]
    fallback_calls = []

    def per_repo(repo):
        fallback_calls.append(repo.name)
        if repo.name == "broken":
            raise RuntimeError("persistent failure")
        return [f"{repo.name}-rec"]

    with pytest.raises(PartialOrgFetchError) as excinfo:
        _fetch_org(client, per_repo)

    # The org path builds context from the bare repo name.
    assert excinfo.value.records == [("done", 1), ("partway", 30), "flaky-rec"]
    assert [r.name for r in excinfo.value.failed_repos] == ["partway", "broken"]
    assert "partway" not in fallback_calls  # its pages were kept, not refetched from page 1
    assert sorted(set(fallback_calls)) == ["broken", "flaky"]


def test_org_fetch_survives_resource_errors_and_502s_without_the_fallback(monkeypatch):
    """The 14 Oct cold-run failure modes, end to end: every repo completes and no work is thrown away."""
    repos = [_repo(name) for name in ("a", "b", "c", "solo")]
    monkeypatch.setattr(batched._common, "fetch_org_repos_graphql", lambda *_a, **_k: repos)
    client = Mock()
    client.graphql.side_effect = [
        # Round 1: a and b finish; c runs over the resource limit; solo pages on.
        GraphQLResponseError(
            {
                "data": {"r0": _page([1]), "r1": _page([2]), "r2": None, "r3": _page([40], has_next=True, cursor="S1")},
                "errors": [_resource_limits(["r2", "issues"])],
            }
        ),
        # Round 2 (page 50, width 2: c and solo) and round 3 (page 25, width 1: c) time out.
        GitHubServerError("502"),
        GitHubServerError("502"),
        # Rounds 4 and 5 (page 12, width 1): c, then solo, finish.
        {"data": {"r2": _page([3])}},
        {"data": {"r3": _page([41])}},
    ]

    def per_repo(repo):
        raise AssertionError(f"fallback must not run, but it did for {repo.full_name}")

    records = _fetch_org(client, per_repo)

    assert records == [("a", 1), ("b", 2), ("c", 3), ("solo", 40), ("solo", 41)]
    sent = [call[0][1] for call in client.graphql.call_args_list]
    assert sent[-1]["c3"] == "S1"  # solo resumed from its last good cursor
    assert [v["pageSize"] for v in sent] == [100, 50, 25, 12, 12]


def test_releases_never_cache_a_repo_the_batch_left_partway(monkeypatch, tmp_path):
    """A repo the batch failed partway is refetched whole by the fallback; its partial page is not cached or doubled."""
    from hiero_analytics.data_sources import cache
    from hiero_analytics.data_sources.github_ingest import releases

    monkeypatch.setattr(cache, "GITHUB_CACHE_DIR", tmp_path / "github")
    monkeypatch.setattr(releases, "fetch_org_repos_graphql", lambda *_a, **_k: [_repo("lib")])

    def _release(tag):
        return {"tagName": tag, "name": tag, "publishedAt": "2026-10-01T00:00:00Z", "isDraft": False}

    def _releases_page(tags, cursor=None):
        return {"releases": {"pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor}, "nodes": tags}}

    client = Mock()
    client.graphql.side_effect = [
        {"data": {"r0": _releases_page([_release("v1")], cursor="P1")}},
        {"data": {"r0": _releases_page([_release("v2")], cursor="P1")}},  # stalls
        {"data": {"r0": _releases_page([_release("v2")], cursor="P1")}},  # and stalls on the resume
        # The single-repo fallback starts over from page 1.
        {"data": {"repository": _releases_page([_release("v1")], cursor="Q1")}},
        {"data": {"repository": _releases_page([_release("v2")])}},
    ]

    fetched = releases.fetch_org_releases_graphql(client, "org", max_workers=1, use_cache=True)

    assert sorted(r.tag_name for r in fetched) == ["v1", "v2"]  # once each
    cached = cache.load_records_cache(
        releases.RELEASES_RESOURCE, "org_lib", {"owner": "org", "repo": "lib"}, ReleaseRecord, use_cache=True
    )
    assert sorted(r.tag_name for r in cached) == ["v1", "v2"]  # the whole repo, not the batch's page 1


def test_an_unreadable_page_fails_that_repo_and_spares_the_rest():
    """A node the model cannot hydrate fails its repo only; it no longer escapes and aborts the whole fetch."""

    class _PickyModel:
        @classmethod
        def from_github_node(cls, node, context):
            if node["id"] == "bad":
                raise KeyError("title")
            return [(context["repo"], node["id"])]

    client = Mock()
    client.graphql.return_value = {"data": {"r0": _page([1]), "r1": _page(["bad"])}}

    records, failed = batched.fetch_repos_batched(
        client, [_repo("a"), _repo("b")], _QUERY, _PickyModel, ["issues"], lambda repo: {"repo": repo.full_name}
    )

    assert records == [("org/a", 1)]
    assert [r.name for r in failed] == ["b"]
