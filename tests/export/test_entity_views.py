"""Repository and contributor documents, as published through the data API."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

import hiero_analytics.pipelines.entity_activity as runner
from hiero_analytics.dashboard_spec import entities as spec
from hiero_analytics.data_sources.models import ContributorActivityRecord, IssueTimelineEventRecord
from hiero_analytics.export import data_api
from hiero_analytics.export.data_api import API_VERSION, emit_data_api
from hiero_analytics.export.entity_views import build_entity_documents, entity_id

ORG = "test-org"


def _act(repo, actor, activity_type, days_ago, target_author=None):
    return ContributorActivityRecord(
        repo=f"{ORG}/{repo}",
        activity_type=activity_type,
        actor=actor,
        occurred_at=datetime.now(UTC) - timedelta(days=days_ago),
        target_type="pull_request",
        target_number=1,
        target_author=target_author or actor,
    )


RECORDS = [
    _act("hiero-sdk-js", "Alice", "authored_pull_request", 2),
    _act("hiero-sdk-js", "bob", "reviewed_pull_request", 2, target_author="Alice"),
    _act("hiero-sdk-js", "bob", "merged_pull_request", 2, target_author="Alice"),
    _act("hiero-sdk-js", "Alice", "authored_issue", 200),
    _act(".github", "bob", "authored_pull_request", 800),
]
LABELS = [
    IssueTimelineEventRecord(
        repo=f"{ORG}/hiero-sdk-js",
        issue_number=4,
        event_type="labeled",
        occurred_at=datetime.now(UTC) - timedelta(days=10),
        label="good first issue",
        actor="carol",
    )
]


@pytest.fixture
def org_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The entity tables the pipeline writes for RECORDS, in a sandboxed output tree."""
    org_dir = tmp_path / "data" / "org" / ORG
    org_dir.mkdir(parents=True)
    monkeypatch.setattr(runner, "org_context", lambda _org: (None, org_dir))
    monkeypatch.setattr(runner, "load_contributor_activity", lambda _client, _org: RECORDS)
    monkeypatch.setattr(runner, "load_issue_label_events", lambda _client, _org: LABELS)
    runner.main(ORG)
    return org_dir


def _build(org_data: Path):
    built = build_entity_documents(ORG, org_data, data_api._freshness)
    assert built is not None
    return built


def _related_tables(org_data: Path) -> None:
    pd.DataFrame(
        {
            "repo": [f"{ORG}/hiero-sdk-js"],
            "latest_release": ["2026-07-01"],
            "days_since_last_release": [4],
            "median_gap_days": [12],
            "release_status": ["released"],
        }
    ).to_csv(org_data / "release_repo_summary.csv", index=False)
    Path(f"{org_data / 'release_repo_summary.csv'}.meta.json").write_text(
        json.dumps({"generated_at": "2026-07-25T10:00:00+00:00"})
    )
    pd.DataFrame(
        {
            "repo": [f"{ORG}/hiero-sdk-js"] * 3,
            "tag_name": ["v1", "v3", "v2"],
            "published_at": ["2026-01-01", "2026-07-01", "2026-04-01"],
            "is_prerelease": [False, False, True],
        }
    ).to_csv(org_data / "release_timeline.csv", index=False)
    # Governance keys repositories by bare name; both spellings match.
    pd.DataFrame({"repo": ["hiero-sdk-js"], "Good First Issue": [3], "Beginner": [1]}).to_csv(
        org_data / "difficulty_by_repo.csv", index=False
    )
    pd.DataFrame(
        {"repo": ["hiero-sdk-js"], "user": ["bob"], "granted_role": ["maintainer"], "status": ["active"]}
    ).to_csv(org_data / "role_coverage_all.csv", index=False)
    pd.DataFrame({"repo": ["hiero-sdk-js"], "distinct_orgs": [2], "top_org": ["Hashgraph"]}).to_csv(
        org_data / "repo_affiliation_diversity.csv", index=False
    )
    pd.DataFrame(
        {"repo": ["hiero-sdk-js"], "maintainers": [4], "committers": [9], "triage": [2], "active_recent": [6]}
    ).to_csv(org_data / "repo_activity_overview.csv", index=False)
    pd.DataFrame(
        {"repo": [f"{ORG}/hiero-sdk-js"], "distinct_hips_merged": [7], "matched_prs": [30], "total_prs": [900]}
    ).to_csv(org_data / "hip_repo_engagement.csv", index=False)


def test_ids_are_safe_file_names():
    """Entity ids are lower-case, path-safe file names."""
    assert entity_id("hiero-ledger/hiero-sdk-js") == "hiero-sdk-js"
    assert entity_id("Alice") == "alice"
    assert entity_id("hiero-ledger/.github") == "_github"
    # Only the last path segment is ever used, and it can never be "." or "..".
    assert entity_id("../etc") == "etc"
    assert entity_id("..") is None
    assert entity_id(".") is None
    assert entity_id("a/b c") is None


def test_indexes_list_every_entity_with_its_detail_path(org_data):
    """Each index lists its entities and where their documents live."""
    built = _build(org_data)
    assert built.manifest_entry == {
        "repositories": {"path": f"{ORG}/entities/repositories.json", "count": 2},
        "contributors": {"path": f"{ORG}/entities/contributors.json", "count": 3},
    }
    index = built.documents[f"{ORG}/entities/contributors.json"]
    assert index["schema_version"] == 1
    assert index["detail_path"] == f"{ORG}/entities/contributors/{{id}}.json"
    assert [row["id"] for row in index["rows"]] == ["alice", "bob", "carol"]
    assert index["rows"][0]["login"] == "Alice"
    assert "generated_at" in index and index["stale"] is False
    repos = built.documents[f"{ORG}/entities/repositories.json"]["rows"]
    assert {row["id"]: row["name"] for row in repos} == {"_github": ".github", "hiero-sdk-js": "hiero-sdk-js"}
    for row in repos:
        assert f"{ORG}/entities/repositories/{row['id']}.json" in built.documents


def test_repository_document_counts_windows_from_events(org_data):
    """A repository's windows, work mix and contributor table come from its events."""
    document = _build(org_data).documents[f"{ORG}/entities/repositories/hiero-sdk-js.json"]
    assert (document["kind"], document["full_name"]) == ("repository", f"{ORG}/hiero-sdk-js")
    assert document["github_url"] == f"https://github.com/{ORG}/hiero-sdk-js"
    week, year, all_time = (document["summary"][key] for key in ("7d", "365d", "all"))
    assert (week["prs_opened"], week["reviews_given"], week["merges_done"], week["active_contributors"]) == (1, 1, 1, 2)
    assert (year["issues_opened"], year["labels_applied"], year["active_contributors"]) == (1, 1, 3)
    assert all_time["total_actions"] == 5
    assert document["mix"]["7d"]["reviewing_and_guiding"] == {"count": 2, "share": 67}
    contributors = document["contributors"]
    assert {row["contributor"] for row in contributors["periods"]["7d"]} == {"Alice", "bob"}
    assert {row["contributor"] for row in contributors["rows"]} == {"Alice", "bob", "carol"}
    assert contributors["columns"][0] == {"key": "contributor", "label": "Contributor"}


def test_documents_state_scope_source_window_and_methodology(org_data):
    """Every detail document says what it counts, from where, over which dates."""
    document = _build(org_data).documents[f"{ORG}/entities/contributors/alice.json"]
    assert "does not measure commits, comments, reactions" in document["scope"]
    assert "individual performance" in document["scope"]
    assert document["methodology"] and document["population"]
    assert spec.PAIR_ACTIVITY_FILE in document["source"]
    periods = {period["key"]: period for period in document["window"]["periods"]}
    assert set(periods) == {"7d", "30d", "365d", "all"}
    end = datetime.fromisoformat(document["window"]["end"])
    assert datetime.fromisoformat(periods["7d"]["start"]) == end - timedelta(days=7)
    assert document["window"]["data_through"]
    assert "generated_at" in document


def test_a_window_without_activity_is_zeros_not_missing(org_data):
    """A quiet window is published as zeros, and its tables as empty lists."""
    document = _build(org_data).documents[f"{ORG}/entities/repositories/_github.json"]
    assert document["summary"]["30d"] == {
        "prs_opened": 0,
        "reviews_given": 0,
        "merges_done": 0,
        "issues_opened": 0,
        "labels_applied": 0,
        "total_actions": 0,
        "active_contributors": 0,
    }
    assert document["mix"]["30d"]["building_and_fixing"] == {"count": 0, "share": 0}
    assert document["contributors"]["periods"]["7d"] == []


def test_contributor_document_breaks_activity_down_by_repository(org_data):
    """A contributor's document lists each repository they acted in, per window."""
    document = _build(org_data).documents[f"{ORG}/entities/contributors/bob.json"]
    assert (document["login"], document["summary"]["all"]["repos_touched"]) == ("bob", 2)
    assert document["summary"]["all"]["merges_done"] == 1
    repos = document["repositories"]
    assert [row["repo"] for row in repos["rows"]] == [f"{ORG}/hiero-sdk-js", f"{ORG}/.github"]
    assert [row["repo"] for row in repos["periods"]["30d"]] == [f"{ORG}/hiero-sdk-js"]
    assert document["first_active"] < document["last_active"]


def test_trend_is_a_valid_monthly_chart_document(org_data):
    """The trend is a gap-filled monthly timeseries the dashboard's charts accept."""
    trend = _build(org_data).documents[f"{ORG}/entities/contributors/alice.json"]["trend"]
    assert (trend["schema_version"], trend["kind"], trend["frequency"]) == (1, "timeseries", "month")
    assert [series["key"] for series in trend["series"]] == list(spec.COUNT_LABELS)
    buckets = [row["bucket"] for row in trend["rows"]]
    # Gap-filled from the first active month to the generation month.
    assert buckets == sorted(buckets) and len(buckets) >= 7
    assert sum(row["prs_opened"] for row in trend["rows"]) == 1
    assert trend["rows"][-1]["partial"] is True


def test_related_sections_join_available_tables_and_name_the_missing(org_data):
    """Optional per-repository tables join by name; an unproduced one is named."""
    _related_tables(org_data)
    document = _build(org_data).documents[f"{ORG}/entities/repositories/hiero-sdk-js.json"]
    related = {section["id"]: section for section in document["related"]}
    releases = related["releases"]
    assert {field["key"]: field["value"] for field in releases["fields"]}["days_since_last_release"] == 4
    assert [row["tag_name"] for row in releases["list"]["rows"]] == ["v3", "v2", "v1"]
    assert releases["generated_at"] == "2026-07-25T10:00:00+00:00"
    governance = related["governance"]
    # Role counts with the active share lead; affiliation facts join from their own table.
    assert [field["key"] for field in governance["fields"]] == [
        "maintainers",
        "committers",
        "triage",
        "active_recent",
        "distinct_orgs",
        "top_org",
    ]
    assert governance["list"]["rows"] == [{"user": "bob", "granted_role": "maintainer", "status": "active"}]
    hips = {field["key"]: field["value"] for field in related["hips"]["fields"]}
    assert hips == {"distinct_hips_merged": 7, "matched_prs": 30, "total_prs": 900}
    onboarding = {field["key"]: field["value"] for field in related["onboarding"]["fields"]}
    assert onboarding == {"Good First Issue": 3, "Beginner": 1}
    # The scorecard pipeline did not run: said so, never silently blank.
    assert document["unavailable"] == ["Security"]
    # A repository with no row in a produced table gets the section with no fields.
    other = _build(org_data).documents[f"{ORG}/entities/repositories/_github.json"]
    assert {section["id"]: section["fields"] for section in other["related"]}["releases"] == []


def test_no_entity_tables_means_no_documents(tmp_path):
    """Without the pipeline's tables there is nothing to publish."""
    assert build_entity_documents(ORG, tmp_path, data_api._freshness) is None


def test_emit_publishes_entity_documents_and_lists_them_in_the_manifest(
    org_data, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The emit writes every document, lists the indexes and clears stale ones."""
    monkeypatch.setattr(data_api.paths, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(data_api.paths, "ORG_DATA_DIR", tmp_path / "data" / "org")
    monkeypatch.setattr(data_api.paths, "ORG", ORG)
    widgets = {
        "id": "widgets",
        "file": "widgets.csv",
        "title": "Widgets",
        "description": "All widgets.",
        "columns": [("name", "widget")],
    }
    family = type(
        "Family",
        (),
        {
            "SECTION_SPECS": [widgets],
            "SECTION_ORDER": ["widgets"],
            "SECTION_GROUP_OF": {"widgets": "A group"},
            "CHART_MACRO": {"name": "Testing", "charts": {}},
        },
    )
    monkeypatch.setattr(data_api, "TABLE_FAMILIES", {"Testing": family})
    monkeypatch.setattr(data_api, "CHART_MACROS", [{"name": "Testing", "charts": {}}])
    monkeypatch.setattr(data_api, "CUSTOM_VIEW_MODULES", {})
    pd.DataFrame({"name": ["a"]}).to_csv(org_data / "widgets.csv", index=False)
    api_dir = tmp_path / "data" / "api" / API_VERSION
    # A document left by an earlier run for a repository no longer in the data.
    stale = api_dir / ORG / "entities" / "repositories" / "retired.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}")

    manifest = json.loads(emit_data_api().read_text())

    entry = manifest["orgs"][ORG]["entities"]
    assert entry["repositories"]["count"] == 2
    index = json.loads((api_dir / entry["contributors"]["path"]).read_text())
    for row in index["rows"]:
        detail = json.loads((api_dir / index["detail_path"].format(id=row["id"])).read_text())
        assert detail["id"] == row["id"]
    assert not stale.exists()


def test_related_sections_link_back_to_the_dashboard_sections_they_summarise(org_data):
    """Each joined figure names the published sections its tables feed, and only those."""
    _related_tables(org_data)
    sources = {
        "repo_activity_overview.csv": [{"macro": "Governance", "id": "repoactivity", "title": "Repository activity"}],
        "role_coverage_all.csv": [{"macro": "Governance", "id": "repo", "title": "Roles by repo"}],
        "hip_repo_engagement.csv": [{"macro": "HIPs", "id": "hip-repo-engagement", "title": "HIP engagement"}],
    }
    built = build_entity_documents(ORG, org_data, data_api._freshness, sources)
    related = {
        section["id"]: section
        for section in built.documents[f"{ORG}/entities/repositories/hiero-sdk-js.json"]["related"]
    }
    assert [link["id"] for link in related["governance"]["links"]] == ["repoactivity", "repo"]
    assert related["hips"]["links"] == [{"macro": "HIPs", "id": "hip-repo-engagement", "title": "HIP engagement"}]
    # A table no published section shows links nowhere.
    assert related["onboarding"]["links"] == []


def test_source_sections_name_only_what_the_org_published():
    """Tables map to the card that shows them (absorbed variants to their card); charts by their CSVs."""
    card = {"id": "affiliations", "macro": "Governance", "title": "Organisation affiliations", "row_count": 2}
    index = data_api._source_sections(
        "hiero-ledger",
        [("affiliations.csv", card), ("committer_affiliations.csv", card)],
        [{"id": "hip-repo-engagement", "macro": "HIPs", "title": "Which repositories engage with HIPs"}],
    )
    entry = {"macro": "Governance", "id": "affiliations", "title": "Organisation affiliations"}
    assert index["affiliations.csv"] == [entry]
    assert index["committer_affiliations.csv"] == [entry]
    assert index["hip_repo_engagement.csv"][0]["id"] == "hip-repo-engagement"
    # Chart cards that were not emitted for the org are never linked.
    assert all(
        link["id"] == "hip-repo-engagement" for links in index.values() for link in links if link["macro"] == "HIPs"
    )
