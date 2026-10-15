"""Tests for the aliased multi-repo batched GraphQL engine."""

from unittest.mock import Mock

import pytest

from hiero_analytics.data_sources.dataset_store import PartialOrgFetchError
from hiero_analytics.data_sources.github_client import GitHubServerError
from hiero_analytics.data_sources.github_ingest import batched
from hiero_analytics.data_sources.models import RepositoryRecord
from hiero_analytics.data_sources.pagination import PageSizePolicy
from hiero_analytics.data_sources.queries import load_query

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
    """HasNextPage with a non-advancing cursor hands the repo to the fallback, not an infinite loop."""
    client = Mock()
    client.graphql.side_effect = [
        {"data": {"r0": _page([1], has_next=True, cursor="SAME")}},
        {"data": {"r0": _page([2], has_next=True, cursor="SAME")}},  # cursor did not advance
    ]

    records, failed = batched.fetch_repos_batched(
        client,
        [_repo("a")],
        _QUERY,
        _FakeModel,
        ["issues"],
        lambda repo: {"repo": repo.full_name},
    )

    assert client.graphql.call_count == 2  # terminated, no spin
    assert [r.name for r in failed] == ["a"]
    assert [r[1] for r in records] == [1, 2]


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


def test_batched_round_at_the_floor_reraises_into_the_per_repo_fallback(monkeypatch):
    """A server error that survives shrinking to the floor marks the chunk's repos failed."""
    monkeypatch.setattr(batched, "PageSizePolicy", lambda: PageSizePolicy(100, 25))
    client = Mock()
    client.graphql.side_effect = GitHubServerError("502")

    records, failed = batched.fetch_repos_batched(
        client, [_repo("a"), _repo("b")], _QUERY, _FakeModel, ["issues"], lambda repo: {"repo": repo.full_name}
    )

    assert records == []
    assert [r.name for r in failed] == ["a", "b"]
    assert [call[0][1]["pageSize"] for call in client.graphql.call_args_list] == [100, 50, 25]


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


def test_org_batched_falls_back_per_repo_and_composes_partial(monkeypatch):
    """Failed batch repos retry per-repo; a persistent failure raises with ALL arrived records."""
    ok, broken = _repo("ok"), _repo("broken")
    monkeypatch.setattr(batched._common, "fetch_org_repos_graphql", lambda *_a, **_k: [ok, broken])
    monkeypatch.setattr(batched, "fetch_repos_batched", lambda *_a, **_k: (["batched-rec"], [ok, broken]))

    def per_repo(repo):
        if repo.name == "broken":
            raise RuntimeError("persistent failure")
        return [f"{repo.name}-rec"]

    with pytest.raises(PartialOrgFetchError) as excinfo:
        batched.fetch_org_records_batched(
            Mock(),
            "org",
            query_text=_QUERY,
            model_class=_FakeModel,
            nodes_path=["issues"],
            per_repo=per_repo,
            task_desc="test records",
            max_workers=2,
        )

    assert excinfo.value.records == ["batched-rec", "ok-rec"]
    assert [r.name for r in excinfo.value.failed_repos] == ["broken"]
