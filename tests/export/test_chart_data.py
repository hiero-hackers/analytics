"""Interactive charts retain the source counts and calendar semantics."""

import json

import pandas as pd
import pytest

from hiero_analytics.analysis.network_layout import _graph, network_layout, network_tables
from hiero_analytics.analysis.scorecard_analysis import CHECK_COLUMNS
from hiero_analytics.dashboard_spec.interactive import (
    ACTIVITY_HEATMAP_SOURCES,
    RELEASE_TIMELINE_SOURCES,
    REPO_GROWTH_SOURCES,
    ROLE_ACTIVITY,
    ROLE_BY_REPO,
    SCORECARD_CHECKS,
    role_network,
)
from hiero_analytics.export import data_api
from hiero_analytics.export.chart_data import chart_document


def write_counts(tmp_path, frequency, buckets, counts):
    """Write a small role dataset with one nonzero series."""
    path = tmp_path / "counts.csv"
    pd.DataFrame({frequency: buckets, "general_user": counts, "triage": 0, "committer": 2, "maintainer": 3}).to_csv(
        path, index=False
    )
    return path


def roles(frequency, **extra):
    """The role-activity preset for one calendar resolution."""
    return {**ROLE_ACTIVITY, "category": frequency, "frequency": frequency, **extra}


def test_monthly_window_fills_gaps_and_preserves_counts(tmp_path):
    """Missing calendar months are zero, while populated buckets keep exact values."""
    path = write_counts(tmp_path, "month", ["2026-03", "2026-01"], [7, 4])
    data = chart_document(roles("month", buckets=3), path, "org", "2026-03-15T12:00:00Z")
    assert [row["bucket"] for row in data["rows"]] == ["2026-01", "2026-02", "2026-03"]
    assert [row["general_user"] for row in data["rows"]] == [4, 0, 7]
    assert [row["maintainer"] for row in data["rows"]] == [3, 0, 3]
    assert [row["partial"] for row in data["rows"]] == [False, False, True]
    assert data["dimensions"] == ["period", "series"]


def test_gap_filling_keeps_integer_details_integral(tmp_path):
    """A gap-filled bucket must not turn integer detail counts into 12.0 in the JSON."""
    path = tmp_path / "ts.csv"
    path.write_text("month,prs,reviewers\n2026-01,5,12\n2026-03,7,3\n")
    source = {
        "kind": "timeseries",
        "file": "ts.csv",
        "category": "month",
        "frequency": "month",
        "series": [{"key": "prs", "label": "PRs"}],
        "details": [{"key": "reviewers", "label": "Reviewers"}],
        "metric": "m",
        "unit": "u",
        "population": "p",
    }
    data = chart_document(source, path, "org", "2026-03-15T00:00:00+00:00")
    assert [row["reviewers"] for row in data["rows"]] == [12, 0, 3]
    assert '"reviewers": 12,' in json.dumps(data["rows"][0])


@pytest.mark.parametrize(
    ("frequency", "buckets", "expected"),
    [
        ("day", ["2025-12-31", "2026-01-02"], ["2025-12-31", "2026-01-01", "2026-01-02"]),
        ("week", ["2025-W52", "2026-W02"], ["2025-W52", "2026-W01", "2026-W02"]),
        ("year", ["2024", "2026"], ["2024", "2025", "2026"]),
    ],
)
def test_calendar_boundaries(tmp_path, frequency, buckets, expected):
    """Year boundaries and missing sidecars do not shift historic data to today."""
    path = write_counts(tmp_path, frequency, buckets, [4, 7])
    extra = {} if frequency == "year" else {"buckets": 3}
    data = chart_document(roles(frequency, **extra), path, "org")
    assert [row["bucket"] for row in data["rows"]] == expected


@pytest.mark.parametrize("count", [-1, 1.5, float("inf"), float("nan"), "bad"])
def test_invalid_counts_fail(tmp_path, count):
    """Corrupt numeric data must never silently become chart values."""
    path = write_counts(tmp_path, "year", ["2026"], [count])
    with pytest.raises(ValueError):
        chart_document(roles("year"), path, "org")


def test_duplicate_buckets_fail(tmp_path):
    """Two rows for a single month violate the unique-count contract."""
    path = write_counts(tmp_path, "month", ["2026-01", "2026-01"], [1, 2])
    with pytest.raises(ValueError, match="duplicate"):
        chart_document(roles("month", buckets=12), path, "org")


def test_empty_dataset(tmp_path):
    """Empty source data stays empty instead of inventing a zero history."""
    path = write_counts(tmp_path, "month", [], [])
    data = chart_document(roles("month", buckets=12), path, "org")
    assert data["rows"] == []
    assert data["window"] == {"kind": "calendar", "first": None, "last": None}


def test_cumulative_series_carry_forward_and_flows_fill_zero(tmp_path):
    """A running total holds its level through empty months; new repos in them are zero."""
    path = tmp_path / "repo_growth_timeline.csv"
    pd.DataFrame({"month": ["2026-01-01", "2026-03-01"], "repos_created": [2, 1], "cumulative_repos": [5, 6]}).to_csv(
        path, index=False
    )
    created, total = (
        chart_document(REPO_GROWTH_SOURCES[name], path, "org", "2026-05-02T00:00:00Z")
        for name in ["repos_created_per_month", "cumulative_repo_count"]
    )
    assert [row["bucket"] for row in created["rows"]] == ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]
    assert [row["repos_created"] for row in created["rows"]] == [2, 0, 1, 0, 0]
    assert [row["cumulative_repos"] for row in total["rows"]] == [5, 5, 6, 6, 6]
    assert total["mark"] == "line"


def test_snapshot_series_keep_their_own_dates(tmp_path):
    """Point-in-time counts are neither gap-filled nor flagged as partial buckets."""
    path = tmp_path / "open.csv"
    pd.DataFrame({"date": ["2026-01-04", "2026-01-11", "2026-01-13"], "gfi": [1, 2, 3]}).to_csv(path, index=False)
    source = {
        **ROLE_ACTIVITY,
        "category": "date",
        "frequency": "snapshot",
        "series": [{"key": "gfi", "label": "Good First Issue"}],
        "mark": "area",
    }
    data = chart_document(source, path, "org", "2026-01-13T09:00:00Z")
    assert [row["bucket"] for row in data["rows"]] == ["2026-01-04", "2026-01-11", "2026-01-13"]
    assert not any(row["partial"] for row in data["rows"])
    assert data["series"][0]["color"] == "var(--chart-1)"


def _pipeline_spec(source_dir, **source_overrides):
    """One governance card whose single variant draws from ``counts.csv`` in ``source_dir``."""
    return {
        "name": "Governance",
        "charts": {
            "org": [
                {
                    "id": "maintainer-pipeline",
                    "title": "Pipeline",
                    "description": "Roles",
                    "variants": [("Role counts", [("All time", "roles")])],
                    "sources": {"roles": {**roles("year"), "file": "counts.csv", **source_overrides}},
                }
            ]
        },
    }


def test_chart_note_does_not_replace_counting_rule(tmp_path, monkeypatch):
    """A chart's "how to read this" note sits beside the population rule, never over it."""
    source = tmp_path / "source"
    source.mkdir()
    write_counts(source, "year", ["2026"], [9])
    monkeypatch.setattr(data_api, "CHART_MACROS", [_pipeline_spec(source)])
    monkeypatch.setattr(data_api, "CHART_NOTES", {"roles": "Read the bars left to right."})
    output = tmp_path / "api" / "org"
    result = data_api._org_chart_sections("org", source, output)
    variant = result[0]["charts"][0]["variants"][0]
    assert variant == {
        "label": "All time",
        "interactive": {"kind": "timeseries", "path": "org/charts/roles.json"},
        "note": "Read the bars left to right.",
    }
    document = json.loads((output / "charts/roles.json").read_text())
    assert document["id"] == "roles"
    assert document["rows"][0]["general_user"] == 9
    assert document["note"] == "Read the bars left to right."
    assert "Bots are excluded" in document["population"]


def test_a_variant_without_its_dataset_is_not_listed(tmp_path, monkeypatch):
    """A card whose pipeline did not run for this org drops out rather than rendering empty."""
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(data_api, "CHART_MACROS", [_pipeline_spec(source)])
    output = tmp_path / "api" / "org"
    assert data_api._org_chart_sections("org", source, output) == []
    assert not (output / "charts").exists()


def test_a_dataset_whose_sidecar_records_no_rows_is_not_listed(tmp_path, monkeypatch):
    """An analysis that found nothing writes its CSV, but the tab stays off the card."""
    source = tmp_path / "source"
    source.mkdir()
    write_counts(source, "year", [], [])
    (source / "counts.csv.meta.json").write_text(
        json.dumps({"generated_at": "2026-01-01T00:00:00+00:00", "record_count": 0})
    )
    monkeypatch.setattr(data_api, "CHART_MACROS", [_pipeline_spec(source)])
    assert data_api._org_chart_sections("org", source, tmp_path / "api" / "org") == []


def test_a_network_without_its_edge_list_is_not_listed(tmp_path, monkeypatch):
    """Both files a network reads must exist; a half-written pair is absent, not an error."""
    source = tmp_path / "source"
    source.mkdir()
    pd.DataFrame(
        {"repo": ["a"], "active_members": [1], "total_members": [1], "category": ["Other"], "x": [0.0], "y": [0.0]}
    ).to_csv(source / "net_nodes.csv", index=False)
    spec = _pipeline_spec(source)
    spec["charts"]["org"][0]["sources"]["roles"] = {
        **role_network("maintainer", "maintainers"),
        "file": "net_nodes.csv",
        "edges_file": "net_edges.csv",
    }
    monkeypatch.setattr(data_api, "CHART_MACROS", [spec])
    assert data_api._org_chart_sections("org", source, tmp_path / "api" / "org") == []


def test_an_invalid_dataset_is_a_contract_error(tmp_path, monkeypatch):
    """A produced CSV that no longer fits its spec fails the emit loudly."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "counts.csv").write_text("year,unrelated\n2026,1\n")
    monkeypatch.setattr(data_api, "CHART_MACROS", [_pipeline_spec(source)])
    with pytest.raises(data_api.DataApiContractError, match="counts.csv"):
        data_api._org_chart_sections("org", source, tmp_path / "api" / "org")


def test_ranked_categories_keep_every_row(tmp_path):
    """No pooling: summing people across repos would double-count, so every row survives."""
    path = tmp_path / "repos.csv"
    pd.DataFrame(
        {"repo": ["org/big", "org/small"], "general_user": [9, 1], "triage": 0, "committer": 0, "maintainer": 0}
    ).to_csv(path, index=False)
    data = chart_document({**ROLE_BY_REPO, "window": 30, "strip_org_prefix": True}, path, "org", "2026-03-15T12:00Z")
    assert data["kind"] == "categories"
    assert [row["repo"] for row in data["rows"]] == ["big", "small"]
    assert data["window"] == {"kind": "trailing", "days": 30, "end": "2026-03-15T12:00Z"}
    assert (data["rank"], data["top_n"], data["orientation"]) == (True, 10, "horizontal")
    assert data["dimensions"] == ["repo", "series"]


def test_groups_keep_cohorts_apart(tmp_path):
    """A funnel's cohorts share stage names, so uniqueness is per cohort, and the default must exist."""
    path = tmp_path / "funnel.csv"
    pd.DataFrame(
        {
            "cohort": ["all", "all", "recent", "recent"],
            "stage": ["proposed", "approved", "proposed", "approved"],
            "hips": [10, 5, 4, 1],
            "pct_of_proposed": [100, 50, 100, 25],
        }
    ).to_csv(path, index=False)
    source = {
        **ROLE_BY_REPO,
        "category": "stage",
        "category_label": "Stage",
        "group": {"key": "cohort", "label": "Cohort", "default": "recent"},
        "series": [{"key": "hips", "label": "HIPs"}],
        "details": [{"key": "pct_of_proposed", "label": "Share", "format": "percent"}],
    }
    data = chart_document(source, path, "org")
    assert data["group"]["values"] == ["all", "recent"]
    assert data["rows"][1] == {"stage": "approved", "cohort": "all", "hips": 5, "pct_of_proposed": 50}
    assert data["dimensions"] == ["stage", "cohort"]
    with pytest.raises(ValueError, match="absent"):
        chart_document({**source, "group": {**source["group"], "default": "none"}}, path, "org")


def test_decimal_values_and_column_series(tmp_path):
    """Scores may be fractional; ``series: columns`` takes every non-category column in order."""
    path = tmp_path / "scores.csv"
    pd.DataFrame({"repo": ["a", "b"], "score": [7.5, 3.25]}).to_csv(path, index=False)
    data = chart_document({**ROLE_BY_REPO, "series": "columns", "values": "number"}, path, "org")
    assert [row["score"] for row in data["rows"]] == [7.5, 3.25]
    assert data["value_format"] == "decimal"
    assert [series["key"] for series in data["series"]] == ["score"]


def test_duplicates_and_undeclared_renderers_fail(tmp_path):
    """A repo listed twice, or an unknown kind or mark, fails the export."""
    path = tmp_path / "repos.csv"
    pd.DataFrame({"repo": ["a", "a"], "general_user": 1, "triage": 0, "committer": 0, "maintainer": 0}).to_csv(
        path, index=False
    )
    with pytest.raises(ValueError, match="duplicate"):
        chart_document(ROLE_BY_REPO, path, "org")
    with pytest.raises(ValueError, match="Unknown"):
        chart_document({**ROLE_BY_REPO, "kind": "pie"}, path, "org")
    with pytest.raises(ValueError, match="mark"):
        chart_document({**ROLE_BY_REPO, "mark": "donut"}, path, "org")


def test_matrix_takes_month_columns_in_order_and_nulls_inconclusive(tmp_path):
    """Months are found by shape, oldest first; Scorecard's -1 is absent, never a score."""
    heat = tmp_path / "heat.csv"
    pd.DataFrame(
        {
            "contributor name": ["ann", "bo"],
            "role": ["Maintainer", None],
            "activity score": [30, 3],
            "2026-02": [20, 0],
            "2026-01": [10, 3],
        }
    ).to_csv(heat, index=False)
    data = chart_document(ACTIVITY_HEATMAP_SOURCES["contributor_activity_heatmap"], heat, "org")
    assert [column["key"] for column in data["columns"]] == ["2026-01", "2026-02"]
    assert data["rows"][1] == {"contributor name": "bo", "role": "", "activity score": 3, "2026-02": 0, "2026-01": 3}
    assert data["scale"] == {"min": 0, "max": 20, "steps": 5}
    assert data["avatars"] is True
    assert "not a count" in data["population"]

    checks = tmp_path / "checks.csv"
    pd.DataFrame(
        {"repo": ["org/a"], "score": [6.4], **{check: [-1 if check == "Fuzzing" else 5] for check in CHECK_COLUMNS}}
    ).to_csv(checks, index=False)
    data = chart_document(SCORECARD_CHECKS, checks, "org")
    row = data["rows"][0]
    assert row["repo"] == "a"
    assert row["Fuzzing"] is None and row["Maintained"] == 5
    assert (data["scale"]["max"], data["missing"], data["value_format"]) == (10, "Not scored", "decimal")


def test_count_matrix_with_a_blank_cell_keeps_integer_counts(tmp_path):
    """One unreported cell must not turn the rest of its column into floats."""
    path = tmp_path / "mx.csv"
    path.write_text("repo,2026-01,2026-02\na,12,\nb,3,4\n")
    source = {
        "kind": "matrix",
        "file": "mx.csv",
        "row": "repo",
        "row_label": "Repo",
        "columns": "months",
        "value_label": "v",
        "metric": "m",
        "unit": "u",
        "population": "p",
    }
    data = chart_document(source, path, "org")
    assert json.dumps(data["rows"]) == json.dumps(
        [{"repo": "a", "2026-01": 12, "2026-02": None}, {"repo": "b", "2026-01": 3, "2026-02": 4}]
    )


def test_network_tables_carry_the_layout(tmp_path):
    """The saved positions are the packed layout's own, so the dashboard draws the computed picture."""
    nodes = pd.DataFrame(
        {
            "repo": ["hiero-sdk-js", "hiero-sdk-go", "governance"],
            "active_members": [3, 1, 0],
            "total_members": [4, 2, 1],
        }
    )
    edges = pd.DataFrame({"repo_a": ["hiero-sdk-js"], "repo_b": ["hiero-sdk-go"], "shared": [2]})
    node_table, edge_table = network_tables(nodes, edges)
    pos, isolated, caption = network_layout(_graph(nodes, edges))
    assert isolated == ["governance"] and caption is not None
    for row in node_table.itertuples():
        assert (row.x, row.y) == (round(pos[row.repo][0], 4), round(pos[row.repo][1], 4))
    assert list(node_table["category"]) == ["SDKs", "SDKs", "Governance"]

    node_table.to_csv(tmp_path / "net_nodes.csv", index=False)
    edge_table.to_csv(tmp_path / "net_edges.csv", index=False)
    source = role_network("maintainer", "maintainers") | {"edges_file": "net_edges.csv"}
    data = chart_document(source, tmp_path / "net_nodes.csv", "org")
    assert data["edges"] == [{"source": "hiero-sdk-js", "target": "hiero-sdk-go", "shared": 2}]
    assert [category["key"] for category in data["categories"]] == ["SDKs", "Governance"]
    governance = data["nodes"][2]
    assert (governance["id"], governance["active"], governance["total"]) == ("governance", 0, 1)
    assert (governance["x"], governance["y"]) == (round(pos["governance"][0], 4), round(pos["governance"][1], 4))

    pd.DataFrame({"repo_a": ["hiero-sdk-js"], "repo_b": ["elsewhere"], "shared": [1]}).to_csv(
        tmp_path / "net_edges.csv", index=False
    )
    with pytest.raises(ValueError, match="not a node"):
        chart_document(source, tmp_path / "net_nodes.csv", "org")


def test_events_keep_the_trailing_window_busiest_first(tmp_path):
    """Only releases inside the window survive; rows are ordered by release count."""
    path = tmp_path / "release_timeline.csv"
    pd.DataFrame(
        {
            "repo": ["org/a", "org/a", "org/b", "org/c"],
            "tag_name": ["v1", "v2-rc", "v9", "old"],
            "published_at": [
                "2026-03-01T00:00:00Z",
                "2026-03-10T00:00:00Z",
                "2026-03-09T00:00:00Z",
                "2025-01-01T00:00:00Z",
            ],
            "is_prerelease": [False, True, False, False],
        }
    ).to_csv(path, index=False)
    week = RELEASE_TIMELINE_SOURCES["release_timeline_30d"]
    data = chart_document(week, path, "org", "2026-03-15T00:00:00+00:00")
    assert data["categories"] == ["a", "b"]
    assert [(row["repo"], row["tag_name"], row["type"]) for row in data["rows"]] == [
        ("a", "v1", "release"),
        ("b", "v9", "release"),
        ("a", "v2-rc", "prerelease"),
    ]
    assert data["window"] == {"kind": "trailing", "days": 30, "end": "2026-03-15T00:00:00+00:00"}
    pd.DataFrame(
        {"repo": ["a"], "tag_name": ["v1"], "published_at": ["2026-03-01"], "is_prerelease": ["maybe"]}
    ).to_csv(path, index=False)
    with pytest.raises(ValueError, match="true or false"):
        chart_document(week, path, "org")


def test_comparison_skips_the_partial_bucket(tmp_path):
    """The comparable pair is the last two complete buckets, never the current one."""
    path = write_counts(tmp_path, "month", ["2026-01", "2026-02", "2026-03"], [4, 5, 6])
    data = chart_document(roles("month", buckets=3), path, "org", "2026-03-15T12:00:00Z")
    assert data["comparison"] == {"current": "2026-02", "previous": "2026-01"}
    # One complete bucket has nothing to compare against.
    short = chart_document(roles("month", buckets=2), path, "org", "2026-03-15T12:00:00Z")
    assert short["comparison"] is None


def test_snapshots_and_opted_out_series_have_no_comparison(tmp_path):
    """Point-in-time counts on irregular dates are not comparable windows."""
    path = tmp_path / "open.csv"
    pd.DataFrame({"date": ["2026-01-04", "2026-01-11", "2026-01-13"], "gfi": [1, 2, 3]}).to_csv(path, index=False)
    source = {**roles("snapshot"), "category": "date", "series": [{"key": "gfi", "label": "GFI"}]}
    assert chart_document(source, path, "org")["comparison"] is None
    counts = write_counts(tmp_path, "year", ["2024", "2025", "2026"], [1, 2, 3])
    assert chart_document(roles("year", compare=False), counts, "org", "2026-05-01T00:00:00Z")["comparison"] is None


def test_dimensions_use_the_focus_vocabulary(tmp_path):
    """Whatever a CSV calls its column, the document names the concept once."""
    heat = tmp_path / "heat.csv"
    pd.DataFrame({"contributor name": ["ann"], "role": ["Maintainer"], "activity score": [3], "2026-01": [3]}).to_csv(
        heat, index=False
    )
    assert chart_document(ACTIVITY_HEATMAP_SOURCES["contributor_activity_heatmap"], heat, "org")["dimensions"] == [
        "contributor",
        "column",
    ]


def test_meter_and_funnel_marks_are_category_only_and_single_series(tmp_path):
    """Part-to-whole and staged forms draw one series over categories, never over time."""
    from hiero_analytics.dashboard_spec.interactive import OWNERSHIP_SOURCES

    path = tmp_path / "org_codeowner_summary.csv"
    pd.DataFrame({"status": ["Present", "Missing"], "count": [29, 15]}).to_csv(path, index=False)
    data = chart_document(OWNERSHIP_SOURCES["org_codeowner_summary"], path, "org")
    assert data["mark"] == "meter"
    # The headline status stays first: a meter reads its first segment as the share.
    assert [row["status"] for row in data["rows"]] == ["Present", "Missing"]
    assert data["rank"] is False

    counts = write_counts(tmp_path, "month", ["2026-01"], [1])
    with pytest.raises(ValueError, match="mark for timeseries"):
        chart_document(roles("month", buckets=1, mark="funnel"), counts, "org", "2026-01-15T00:00:00Z")
    repos = tmp_path / "repos.csv"
    pd.DataFrame({"repo": ["a"], "general_user": 1, "triage": 0, "committer": 0, "maintainer": 0}).to_csv(
        repos, index=False
    )
    with pytest.raises(ValueError, match="exactly one series"):
        chart_document({**ROLE_BY_REPO, "mark": "meter"}, repos, "org")


def test_median_reference_is_computed_from_the_published_rows(tmp_path):
    """The org median follows the data and names its value; unsupported stats fail."""
    path = tmp_path / "org_scorecard.csv"
    pd.DataFrame({"repo": ["a", "b", "c", "d"], "score": [2.0, 5.5, 6.5, 9.0]}).to_csv(path, index=False)
    source = {
        **ROLE_BY_REPO,
        "series": [{"key": "score", "label": "Score"}],
        "values": "number",
        "reference": {"stat": "median", "label": "Org median"},
    }
    assert chart_document(source, path, "org")["reference"] == {"value": 6.0, "label": "Org median 6"}
    with pytest.raises(ValueError, match="reference"):
        chart_document({**source, "reference": {"stat": "mean"}}, path, "org")
    assert chart_document({**source, "value_max": 10}, path, "org")["value_max"] == 10
    fixed = {"value": 50, "label": "Majority"}
    assert chart_document({**source, "reference": fixed}, path, "org")["reference"] == fixed


def test_an_in_memory_table_builds_the_same_chart_as_its_csv(tmp_path):
    """A slice of a larger table charts exactly like the same rows read from a CSV."""
    path = write_counts(tmp_path, "month", ["2026-01", "2026-03"], [4, 7])
    from_file = chart_document(roles("month"), path, "org", "2026-03-10T00:00:00+00:00")
    from_table = chart_document(
        roles("month"), path, "org", "2026-03-10T00:00:00+00:00", table=pd.read_csv(path, dtype={"month": str})
    )
    assert from_table == from_file


def test_an_in_memory_table_only_builds_series_charts(tmp_path):
    """Matrix, network and events documents still read their own files."""
    with pytest.raises(ValueError, match="only build a timeseries or categories"):
        chart_document({"kind": "matrix"}, tmp_path / "x.csv", "org", table=pd.DataFrame())


def test_a_window_with_nothing_in_it_is_not_listed(tmp_path, monkeypatch):
    """Span tabs share one full-record CSV; a tab whose window is empty stays off the card."""
    source = tmp_path / "source"
    source.mkdir()
    pd.DataFrame(
        {
            "repo": ["org/old"],
            "published_at": ["2026-01-01T00:00:00+00:00"],
            "tag_name": ["v1"],
            "is_prerelease": [False],
        }
    ).to_csv(source / "release_timeline.csv", index=False)
    spec = {
        "name": "Releases",
        "charts": {
            "org": [
                {
                    "id": "release-timeline",
                    "title": "Releases",
                    "description": "Timeline",
                    "variants": [
                        ("Release timeline", [("1 year", "release_timeline_365d"), ("Week", "release_timeline_7d")])
                    ],
                    "sources": {
                        "release_timeline_365d": RELEASE_TIMELINE_SOURCES["release_timeline_365d"],
                        "release_timeline_7d": RELEASE_TIMELINE_SOURCES["release_timeline_7d"],
                    },
                }
            ]
        },
    }
    monkeypatch.setattr(data_api, "CHART_MACROS", [spec])
    monkeypatch.setattr(data_api, "_read_meta", lambda _path: {"generated_at": "2026-03-01T00:00:00+00:00"})
    (section,) = data_api._org_chart_sections("org", source, tmp_path / "api" / "org")
    assert [variant["label"] for variant in section["charts"][0]["variants"]] == ["1 year"]


def test_hide_when_all_zero_keeps_an_all_zero_chart_off_the_card(tmp_path, monkeypatch):
    """Zero rows are kept in the data, but a chart that is all zeros is not listed when the source opts in."""
    source = tmp_path / "source"
    source.mkdir()
    pd.DataFrame({"repo": ["a", "b"], "distinct_hips_merged": [0, 0]}).to_csv(source / "engagement.csv", index=False)
    categories = {
        "kind": "categories",
        "file": "engagement.csv",
        "category": "repo",
        "category_label": "Repository",
        "series": [{"key": "distinct_hips_merged", "label": "Distinct HIPs"}],
        "metric": "m",
        "unit": "u",
        "population": "p",
    }

    def spec(**extra):
        return {
            "name": "HIPs",
            "charts": {
                "org": [
                    {
                        "id": "engagement",
                        "title": "Engagement",
                        "description": "d",
                        "variants": [("Repositories", [("All", "engagement")])],
                        "sources": {"engagement": {**categories, **extra}},
                    }
                ]
            },
        }

    monkeypatch.setattr(data_api, "CHART_MACROS", [spec(hide_when_all_zero=True)])
    assert data_api._org_chart_sections("org", source, tmp_path / "api" / "org") == []
    monkeypatch.setattr(data_api, "CHART_MACROS", [spec()])
    (section,) = data_api._org_chart_sections("org", source, tmp_path / "api2" / "org")
    assert [variant["label"] for variant in section["charts"][0]["variants"]] == ["All"]
