"""Tests for the lfdt-report skill's derive.py (releases, months, period, hips, single-employer)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "lfdt-report" / "scripts"


@pytest.fixture(scope="module")
def derive():
    """Load derive.py from the skill directory."""
    spec = importlib.util.spec_from_file_location("derive", SCRIPTS / "derive.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write(tmp_path: Path, name: str, doc: dict) -> str:
    """Write a fixture document and return its path as a string."""
    path = tmp_path / name
    path.write_text(json.dumps(doc))
    return str(path)


def _event(repo: str, time: str, kind: str = "release") -> dict:
    """One release-timeline row."""
    return {"repo": repo, "time": time, "tag_name": "v1", "type": kind}


def _release_doc() -> dict:
    """A release timeline generated in October 2026 with events either side of the Jan-Feb 2026 range."""
    return {
        "id": "release_timeline",
        "kind": "events",
        "generated_at": "2026-10-06T09:14:03+00:00",
        "window": {"kind": "trailing", "days": 548, "end": "2026-10-06T09:14:03+00:00"},
        "rows": [
            _event("solo", "2025-12-31T23:59:59Z"),  # before the range
            _event("solo", "2026-01-01T00:00:00Z"),  # first instant of the range
            _event("solo", "2026-01-15T10:00:00Z"),
            _event("sdk", "2026-02-28T23:59:59Z", "prerelease"),  # last instant of the range
            _event("sdk", "2026-02-10T10:00:00Z"),
            _event("sdk", "2026-02-11T10:00:00Z", "prerelease"),
            _event("docs", "2026-01-20T10:00:00Z"),
            _event("solo", "2026-03-01T00:00:00Z"),  # after the range
            _event("sdk", "2026-03-20T00:00:00Z", "prerelease"),
        ],
    }


def _monthly_doc() -> dict:
    """A monthly timeseries whose newest bucket (2026-04) is partial and that carries a comparison pair."""
    values = {
        "2025-12": (10, 1),
        "2026-01": (20, 2),
        "2026-02": (15, 2),
        "2026-03": (30, 5),
        "2026-04": (4, 1),
    }
    rows = [{"bucket": m, "a": a, "b": b, "partial": m == "2026-04"} for m, (a, b) in values.items()]
    return {
        "id": "pipeline_monthly",
        "kind": "timeseries",
        "frequency": "month",
        "unit": "Unique active contributors",
        "category": {"key": "bucket", "label": "Period"},
        "series": [{"key": "a", "label": "Alpha"}, {"key": "b", "label": "Beta"}],
        "comparison": {"current": "2026-03", "previous": "2026-02"},
        "generated_at": "2026-04-05T00:00:00+00:00",
        "rows": rows,
    }


def _section_doc() -> dict:
    """A section with all-time rows and 7d/30d/365d period tables of different sizes."""
    all_rows = [
        {"repo": "a", "maintainers": 3, "active_maintainers": 0, "flag": True},
        {"repo": "b", "maintainers": 1, "active_maintainers": 1, "flag": False},
        {"repo": "c", "maintainers": 5, "active_maintainers": 2, "flag": True},
        {"repo": "d", "maintainers": 2, "active_maintainers": 0, "flag": True},
    ]
    return {
        "id": "understaffed",
        "row_count": 4,
        "columns": [{"key": "repo"}, {"key": "maintainers"}, {"key": "active_maintainers"}, {"key": "flag"}],
        "rows": all_rows,
        "periods": {"7d": all_rows[:3], "30d": all_rows[:2], "365d": all_rows[:1]},
    }


def _evidence_doc() -> dict:
    """HIP evidence where HIP 1 and 2 count as merged, 3 is open only, 4 is excluded by its cue, 5 is Deferred.

    Merge dates: HIP 1 in 2026-01 and 2025-11, HIP 2 at the last second of 2026-06, HIP 5 at the first second of 2026-07.
    """

    def row(hip: int, state: str, counted: bool, merged: str | None = None) -> dict:
        """One evidence row."""
        return {"hip": hip, "pr_state": state, "counted": counted, "pr_number": hip * 10, "pr_merged_at": merged}

    return {
        "id": "hip-evidence",
        "generated_at": "2026-10-06T09:14:32+00:00",
        "rows": [
            row(1, "MERGED", True, "2026-01-15 10:00:00+00:00"),
            row(1, "MERGED", True, "2025-11-02 10:00:00+00:00"),  # a second merged PR must not count the HIP twice
            row(2, "MERGED", True, "2026-06-30 23:59:59+00:00"),
            row(2, "OPEN", True),
            row(3, "OPEN", True),
            row(4, "MERGED", False, "2026-02-01 00:00:00+00:00"),
            row(5, "MERGED", True, "2026-07-01 00:00:00+00:00"),
        ],
    }


def _funnel_doc(evidence_all: int = 3, evidence_recent: int = 1) -> dict:
    """A categories funnel with two cohorts and the stage-2 methodology that excludes Deferred specs."""
    return {
        "id": "hip_adoption_funnel",
        "kind": "categories",
        "generated_at": "2026-10-06T09:14:32+00:00",
        "series": [{"key": "hips", "label": "HIPs"}],
        "methodology": [
            "Stage 1, proposed: every spec in that cohort.",
            "Stage 2, approved: those whose frontmatter status is Approved, Accepted, Final, or Active.",
        ],
        "rows": [
            {"stage": "proposed", "cohort": "all specs", "hips": 9},
            {"stage": "implementation evidence", "cohort": "all specs", "hips": evidence_all},
            {"stage": "proposed", "cohort": "created since 2024-09", "hips": 4},
            {"stage": "implementation evidence", "cohort": "created since 2024-09", "hips": evidence_recent},
        ],
    }


def _board_doc() -> dict:
    """A hip-board document placing HIP 5 in the Retired column with status Deferred."""
    return {
        "id": "hip-board",
        "generated_at": "2026-10-06T09:14:32+00:00",
        "columns": [
            {"title": "Final", "items": [{"key": 1, "status": "Final"}, {"key": 2, "status": "Approved"}]},
            {"title": "Retired", "items": [{"key": 5, "status": "Deferred"}]},
        ],
    }


def _repo_diversity_doc() -> dict:
    """Four repos: two single-employer by distinct_orgs with no independents, one with an independent, one multi-org."""

    def row(repo: str, orgs: int, independent: int, unknown: int) -> dict:
        """One repodiversity row."""
        return {"repo": repo, "distinct_orgs": orgs, "independent": independent, "unknown": unknown}

    return {
        "id": "repodiversity",
        "rows": [row("r1", 1, 0, 0), row("r2", 1, 0, 0), row("r3", 1, 2, 0), row("r4", 1, 0, 1), row("r5", 3, 0, 0)],
    }


def _team_diversity_doc() -> dict:
    """Teams with no independent column: the single_employer flag separates the readings."""

    def row(team: str, orgs: int, flag: bool) -> dict:
        """One teamdiversity row."""
        return {"team": team, "distinct_orgs": orgs, "unknown": 0, "single_employer": flag}

    return {
        "id": "teamdiversity",
        "rows": [row("t1", 1, True), row("t2", 1, True), row("t3", 1, False), row("t4", 2, False)],
    }


def _hips(
    derive,
    evidence: dict,
    funnel: dict | None = None,
    cohort: str = "all specs",
    board: dict | None = None,
    start: str | None = None,
    end: str | None = None,
):
    """Run hips_report with fixed file names for the documents."""
    return derive.hips_report(evidence, "evidence.json", funnel, "funnel.json", cohort, board, "board.json", start, end)


def _last(lines: list[str]) -> str:
    """The final output line, which every subcommand reserves for the Derived sentence."""
    return lines[-1]


# --- releases -------------------------------------------------------------


def test_releases_counts_inclusive_range_and_sorts_by_releases(derive):
    """Events in the inclusive month range are counted per repo, sorted by releases descending, with a total."""
    out = derive.releases_report(_release_doc(), "r.json", "2026-01", "2026-02")
    table = [line for line in out if line.startswith("|")]
    assert table[2] == "| solo | 2 | 0 |"  # 2 releases beat sdk's 1
    assert table[3] == "| sdk | 1 | 2 |"
    assert table[4] == "| docs | 1 | 0 |"
    assert table[-1] == "| **Total** | **4** | **2** |"


def test_releases_range_edges_are_inclusive(derive):
    """The first instant of the first month and the last second of the last month are inside the range."""
    out = derive.releases_report(_release_doc(), "r.json", "2026-01", "2026-02")
    text = "\n".join(out)
    assert "| solo | 2 | 0 |" in text  # includes 2026-01-01T00:00:00Z but not 2025-12-31T23:59:59Z
    assert "| sdk | 1 | 2 |" in text  # includes 2026-02-28T23:59:59Z


def test_releases_reports_events_excluded_after_to(derive):
    """Events after --to are counted and named by month, and the whole document reconciles."""
    out = derive.releases_report(_release_doc(), "r.json", "2026-01", "2026-02")
    assert "Excluded after 2026-02: 2 events (2026-03: 2)." in out
    assert "Excluded before 2026-01: 1 events." in out
    assert any("6 in range + 1 before + 2 after = 9 events" in line for line in out)


def test_releases_derived_line_states_source_and_exclusion(derive):
    """The Derived line gives the totals, the source document, the range and the exclusion."""
    derived = _last(derive.releases_report(_release_doc(), "r.json", "2026-01", "2026-02"))
    assert derived.startswith("Derived: 4 releases and 2 prereleases across 3 repositories")
    assert "release_timeline (generated 2026-10-06T09:14:03+00:00)" in derived
    assert "2026-01 to 2026-02 inclusive" in derived
    assert "2 events dated after 2026-02 were excluded (2026-03: 2)" in derived


def test_releases_warns_when_range_starts_before_window(derive):
    """A --from earlier than the trailing window start warns that those months are undercounted."""
    out = derive.releases_report(_release_doc(), "r.json", "2025-01", "2026-02")
    assert any(line.startswith("Warning: --from 2025-01 begins before the document's window start") for line in out)


def test_releases_warns_when_to_is_the_generation_month(derive):
    """Ending the range in the month the document was generated is a partial month and says so."""
    out = derive.releases_report(_release_doc(), "r.json", "2026-01", "2026-10")
    assert any(line.startswith("Warning: --to 2026-10 is the month the document was generated") for line in out)
    quiet = derive.releases_report(_release_doc(), "r.json", "2026-01", "2026-09")
    assert not any(line.startswith("Warning") for line in quiet)


def test_releases_empty_range_is_an_error(derive):
    """A range with no events fails rather than printing an all-zero table."""
    with pytest.raises(derive.DeriveError):
        derive.releases_report(_release_doc(), "r.json", "2024-01", "2024-02")


def test_releases_flags_unrecognised_event_types(derive):
    """Events whose type is neither release nor prerelease are left out and called out."""
    doc = _release_doc()
    doc["rows"].append(_event("solo", "2026-01-02T00:00:00Z", "draft"))
    out = derive.releases_report(doc, "r.json", "2026-01", "2026-02")
    assert any("unrecognised type" in line and "draft: 1" in line for line in out)


# --- months ---------------------------------------------------------------


def test_months_skips_partial_bucket_and_names_it(derive):
    """A partial bucket inside the range is left out of the table and named."""
    out = derive.months_report(_monthly_doc(), "m.json", "2026-01", "2026-04", None)
    first_table = out[: out.index("")]  # the per-month table ends at the first blank line
    assert [line.split("|")[1].strip() for line in first_table[2:]] == ["2026-01", "2026-02", "2026-03"]
    assert "Skipped partial months in range: 2026-04." in out
    assert "partial month(s) 2026-04" in _last(out)


def test_months_names_partial_bucket_outside_the_range(derive):
    """When the range ends before the partial bucket, the line says none were skipped and where the partial one is."""
    out = derive.months_report(_monthly_doc(), "m.json", "2026-01", "2026-03", None)
    assert (
        "Skipped partial months in range: none; the document's other partial buckets, outside the range: 2026-04."
        in out
    )
    assert "no partial month fell in the range" in _last(out)


def test_months_min_and_max_carry_their_month(derive):
    """Min and max per series come from the complete months shown, each with its month."""
    out = derive.months_report(_monthly_doc(), "m.json", "2026-01", "2026-04", None)
    assert "| Alpha | 15 | 2026-02 | 30 | 2026-03 |" in out
    assert "| Beta | 2 | 2026-01 (+1 tied) | 5 | 2026-03 |" in out
    assert "| Total (sum of series) | 17 | 2026-02 | 35 | 2026-03 |" in out  # 15+2 and 30+5


def test_months_compare_prints_requested_months(derive):
    """--compare months are printed with every series value, even when they lie outside the range."""
    out = derive.months_report(_monthly_doc(), "m.json", "2026-01", "2026-03", ["2025-12"])
    assert "Comparison months (as asked with --compare):" in out
    assert "| 2025-12 | 10 | 1 | 11 |" in out
    assert "comparison months 2025-12 read from the same document" in _last(out)


def test_months_compare_refuses_a_partial_or_absent_month(derive):
    """A partial or missing comparison month is named and shows no values, so it cannot be compared by accident."""
    out = derive.months_report(_monthly_doc(), "m.json", "2026-01", "2026-03", ["2026-04", "2019-01"])
    assert "| 2026-04 (partial, not used) | n/a | n/a | n/a |" in out
    assert "| 2019-01 (not in the document) | n/a | n/a | n/a |" in out


def test_months_prints_the_documents_own_comparison_as_adjacent_buckets(derive):
    """The document's comparison pair is printed, labelled as two adjacent buckets and never as since-last-report."""
    out = derive.months_report(_monthly_doc(), "m.json", "2026-01", "2026-03", None)
    assert any("two adjacent buckets" in line and "not 'since the last report'" in line for line in out)
    assert "| 2026-02 (previous) | 15 | 2 | 17 |" in out
    assert "| 2026-03 (current) | 30 | 5 | 35 |" in out


def test_months_adds_a_per_month_total_column(derive):
    """Each month's row ends with the sum of its series, under a plain label when people are not stated as disjoint."""
    out = derive.months_report(_monthly_doc(), "m.json", "2026-01", "2026-03", None)
    assert out[0] == "| Month | Alpha | Beta | Total (sum of series) |"
    assert out[2:5] == ["| 2026-01 | 20 | 2 | 22 |", "| 2026-02 | 15 | 2 | 17 |", "| 2026-03 | 30 | 5 | 35 |"]
    assert "Total (sum of series) is the sum of the series within a single month" in _last(out)
    assert "never summed across months" in _last(out)


def test_months_total_is_labelled_distinct_people_only_when_the_document_counts_each_person_once(derive):
    """The people wording is used only when the population statement says each person is counted once per bucket."""
    doc = _monthly_doc()
    doc["population"] = "Each person is counted once per bucket under the highest governance role they hold."
    out = derive.months_report(doc, "m.json", "2026-01", "2026-03", None)
    assert out[0] == "| Month | Alpha | Beta | Total (distinct people, all roles) |"
    assert any(line.startswith("| Total (distinct people, all roles) | 17 |") for line in out)
    assert "valid because the document counts each person once per bucket" in _last(out)
    assert "never summed across months" in _last(out)
    doc["population"] = "A person may appear in several buckets."
    assert derive.months_report(doc, "m.json", "2026-01", "2026-03", None)[0].endswith("| Total (sum of series) |")


def test_months_total_is_not_shown_for_a_missing_value_or_a_single_series(derive):
    """A month with a missing series value has no total, and a one-series document gets no Total column."""
    doc = _monthly_doc()
    doc["rows"][2]["b"] = None  # 2026-02
    out = derive.months_report(doc, "m.json", "2026-01", "2026-03", None)
    assert "| 2026-02 | 15 | n/a | n/a |" in out
    assert "| Total (sum of series) | 22 | 2026-01 | 35 | 2026-03 |" in out  # 2026-02 is left out of min and max
    single = _monthly_doc()
    single["series"] = single["series"][:1]
    assert derive.months_report(single, "m.json", "2026-01", "2026-03", None)[0] == "| Month | Alpha |"


def test_months_without_a_comparison_pair_says_so(derive):
    """A document with no comparison pair prints that fact instead of an empty table."""
    doc = _monthly_doc()
    doc["comparison"] = None
    out = derive.months_report(doc, "m.json", "2026-01", "2026-03", None)
    assert "The document has no `comparison` pair." in out


def test_months_lists_months_missing_from_the_document(derive):
    """Months in the range that the document does not cover are listed, not silently dropped."""
    out = derive.months_report(_monthly_doc(), "m.json", "2025-10", "2026-01", None)
    assert "Months in range not in the document: 2025-10, 2025-11." in out


def test_months_rejects_a_non_monthly_document(derive):
    """A yearly or weekly series is refused because its buckets are not months."""
    doc = _monthly_doc()
    doc["frequency"] = "year"
    with pytest.raises(derive.DeriveError, match="frequency 'year'"):
        derive.months_report(doc, "m.json", "2026-01", "2026-03", None)


def test_months_with_no_complete_month_in_range_is_an_error(derive):
    """A range holding only a partial bucket fails and says what the document covers."""
    with pytest.raises(derive.DeriveError, match="document covers 2025-12 to 2026-04"):
        derive.months_report(_monthly_doc(), "m.json", "2026-04", "2026-04", None)


# --- period ---------------------------------------------------------------


def test_period_counts_every_table(derive):
    """Row counts are printed for all-time and every period, and the Derived line names the chosen table."""
    out = derive.period_report(_section_doc(), "s.json", "365d", [])
    assert "| all-time | 4 |" in out
    assert "| 7d | 3 |" in out
    assert "| 30d | 2 |" in out
    assert "| 365d | 1 |" in out
    assert out[-2].startswith("Derived: 1 rows in the 365d table of understaffed")


def test_period_without_filters_ends_with_a_where_hint_listing_columns(derive):
    """With no --where the output ends with a hint naming the column keys; with one it does not."""
    out = derive.period_report(_section_doc(), "s.json", "all", [])
    assert (
        _last(out)
        == "add --where COL=VALUE to count matching rows; columns: repo, maintainers, active_maintainers, flag"
    )
    no_columns = _section_doc()
    del no_columns["columns"]
    assert _last(derive.period_report(no_columns, "s.json", "all", [])).endswith(
        "columns: repo, maintainers, active_maintainers, flag"
    )
    filtered = derive.period_report(_section_doc(), "s.json", "all", ["maintainers=>1"])
    assert not any(line.startswith("add --where") for line in filtered)
    assert _last(filtered).startswith("Derived:")


def test_period_where_numeric_comparison(derive):
    """Values starting with <, >, <= or >= compare numerically, and all filters must hold."""

    def count(*where: str, period: str = "all") -> int:
        """Matching row count for the given filters in the chosen period."""
        out = derive.period_report(_section_doc(), "s.json", period, list(where))
        line = next(row for row in out if row.startswith(f"| {'all-time' if period == 'all' else period} |"))
        return int(line.split("|")[3])

    assert count("maintainers=<=2") == 2  # b (1) and d (2)
    assert count("maintainers=<2") == 1
    assert count("maintainers=>=3") == 2  # a (3) and c (5)
    assert count("maintainers=>3") == 1
    assert count("maintainers=>=3", "active_maintainers=0") == 1  # a only
    assert count("maintainers=<=2", period="7d") == 1  # d is not in the 7d table


def test_period_where_equality_on_strings_numbers_and_booleans(derive):
    """Equality compares strings exactly, numbers by value and booleans case-insensitively."""
    doc = _section_doc()
    assert derive._filter_rows(doc["rows"], [("repo", "=", "a")])[0] == doc["rows"][:1]
    assert len(derive._filter_rows(doc["rows"], [("maintainers", "=", "3.0")])[0]) == 1
    assert len(derive._filter_rows(doc["rows"], [("flag", "=", "True")])[0]) == 3
    assert len(derive._filter_rows(doc["rows"], [("repo", "=", "A")])[0]) == 0


def test_period_where_derived_line_states_filters_and_counts(derive):
    """The Derived line spells out the filters and the count of matching rows in the chosen period."""
    out = derive.period_report(_section_doc(), "s.json", "7d", ["maintainers=>=3", "active_maintainers=0"])
    assert _last(out).startswith("Derived: 1 of the 3 rows in the 7d table of understaffed")
    assert "match maintainers >= 3 and active_maintainers == 0" in _last(out)


def test_period_where_numeric_test_on_text_does_not_match_and_warns(derive):
    """A numeric comparison on a non-number cell never matches and is reported."""
    out = derive.period_report(_section_doc(), "s.json", "all", ["repo=>3"])
    assert any(line.startswith("Warning: 4 cell(s)") for line in out)
    assert "| all-time | 4 | 0 |" in out


def test_period_unknown_column_is_an_error_with_the_column_list(derive):
    """A mistyped column fails loudly instead of reporting a plausible zero."""
    with pytest.raises(derive.DeriveError, match="columns are: active_maintainers, flag, maintainers, repo"):
        derive.period_report(_section_doc(), "s.json", "all", ["maintainer=1"])


def test_period_operator_before_equals_gets_a_hint(derive):
    """Writing COL<=1 instead of COL=<=1 explains the right form."""
    with pytest.raises(
        derive.DeriveError, match="Write the operator after the equals sign, for example maintainers=<=1"
    ):
        derive.period_report(_section_doc(), "s.json", "all", ["maintainers<=1"])


def test_period_non_numeric_operand_is_an_error(derive):
    """An ordering operator needs a number after it."""
    with pytest.raises(derive.DeriveError, match="is not a number"):
        derive.period_report(_section_doc(), "s.json", "all", ["maintainers=<many"])


def test_period_missing_period_table_is_an_error(derive):
    """Asking for a period the document lacks lists the ones it has."""
    doc = _section_doc()
    del doc["periods"]
    with pytest.raises(derive.DeriveError, match=r"no 30d table \(available: all\)"):
        derive.period_report(doc, "s.json", "30d", [])


def test_period_zero_rows_prompts_a_reading_of_the_description(derive):
    """A zero count adds a note that exception lists and populations read differently."""
    out = derive.period_report(_section_doc(), "s.json", "all", ["maintainers=>99"])
    assert any(line.startswith("Note: zero rows.") for line in out)


def test_period_notes_when_a_period_equals_all_time(derive):
    """A period table identical to the all-time rows is called out (an org younger than the period)."""
    doc = _section_doc()
    doc["periods"]["365d"] = list(doc["rows"])
    out = derive.period_report(doc, "s.json", "365d", [])
    assert any("identical to the all-time rows" in line for line in out)


def test_period_warns_when_row_count_disagrees_with_rows(derive):
    """A row_count that differs from the rows list is flagged."""
    doc = _section_doc()
    doc["row_count"] = 9
    out = derive.period_report(doc, "s.json", "all", [])
    assert any(line.startswith("Warning: row_count says 9 but the all-time rows list has 4") for line in out)


# --- hips -----------------------------------------------------------------


def test_hips_counts_distinct_hips_with_counted_merged_evidence(derive):
    """Only counted rows on merged PRs count, each HIP once, and open or excluded references do not."""
    out = _hips(derive, _evidence_doc())
    assert "| Rows with counted = true and pr_state = MERGED | 4 |" in out
    assert "| Distinct HIP numbers among those rows | 3 |" in out  # HIPs 1, 2 and 5
    assert _last(out).startswith("Derived: 3 distinct HIP numbers have at least one row with counted = true")


def test_hips_matches_pr_state_regardless_of_case(derive):
    """pr_state is compared upper-cased, so a lower-case value still counts."""
    doc = _evidence_doc()
    doc["rows"].append({"hip": 7, "pr_state": "merged", "counted": True})
    assert "| Distinct HIP numbers among those rows | 4 |" in _hips(derive, doc)


def test_hips_difference_against_the_funnel(derive):
    """The funnel's implementation-evidence value and the difference are printed, with the Deferred explanation."""
    out = _hips(derive, _evidence_doc(), _funnel_doc(evidence_all=2))
    assert "| Funnel stage 'implementation evidence', cohort 'all specs' | 2 |" in out
    assert "| Difference (evidence minus funnel) | 1 |" in out
    assert any("excludes Deferred specs" in line and "Stage 2, approved" in line for line in out)
    assert "difference 1" in _last(out)
    assert "so Deferred specs are not in it" in _last(out)


def test_hips_funnel_cohort_can_be_chosen(derive):
    """--cohort picks the other funnel cohort."""
    out = _hips(derive, _evidence_doc(), _funnel_doc(), cohort="created since 2024-09")
    assert "| Funnel stage 'implementation evidence', cohort 'created since 2024-09' | 1 |" in out
    assert "| Difference (evidence minus funnel) | 2 |" in out


def test_hips_omits_the_reason_when_the_funnel_does_not_state_it(derive):
    """If the funnel's methodology does not list the admitted statuses, the difference is printed without a reason."""
    funnel = _funnel_doc(evidence_all=2)
    funnel["methodology"] = ["Stage 1, proposed: every spec in that cohort."]
    out = _hips(derive, _evidence_doc(), funnel)
    assert "| Difference (evidence minus funnel) | 1 |" in out
    assert not any("Deferred" in line for line in out)


def test_hips_board_names_the_hips_the_funnel_excludes(derive):
    """With the board, the counted HIPs outside the funnel's statuses are named and matched to the difference."""
    out = _hips(derive, _evidence_doc(), _funnel_doc(evidence_all=2), board=_board_doc())
    assert any("HIP-5 (Deferred)" in line and "equal to the difference" in line for line in out)
    assert "HIP-5 (Deferred)" in _last(out)


def test_hips_board_says_when_the_gap_is_not_explained(derive):
    """A difference larger than the number of out-of-status HIPs is reported as not fully explained."""
    out = _hips(derive, _evidence_doc(), _funnel_doc(evidence_all=1), board=_board_doc())
    assert any("1 against a difference of 2, so the gap is not fully explained" in line for line in out)


def test_hips_funnel_without_the_stage_is_an_error(derive):
    """A funnel with no implementation-evidence row for the cohort fails and lists the rows it has."""
    funnel = _funnel_doc()
    funnel["rows"] = [r for r in funnel["rows"] if r["stage"] == "proposed"]
    with pytest.raises(derive.DeriveError, match="no stage 'implementation evidence'"):
        _hips(derive, _evidence_doc(), funnel)


def test_hips_rejects_non_boolean_counted_flag(derive):
    """A counted column holding strings fails, since 'false' would otherwise be miscounted as truthy."""
    doc = _evidence_doc()
    doc["rows"][0]["counted"] = "false"
    with pytest.raises(derive.DeriveError, match="expected booleans"):
        _hips(derive, doc)


def test_hips_rejects_a_document_without_evidence_columns(derive):
    """Rows lacking the evidence columns are refused with the missing name."""
    with pytest.raises(derive.DeriveError, match="no 'counted' column"):
        _hips(derive, {"id": "x", "rows": [{"hip": 1, "pr_state": "MERGED"}]})


def test_hips_scopes_evidence_by_merge_month_inclusively(derive):
    """Only counted merged rows whose pr_merged_at month is in the range count; both edges are inclusive."""
    out = _hips(derive, _evidence_doc(), start="2026-01", end="2026-06")
    assert "| Rows with counted = true and pr_state = MERGED | 4 |" in out
    assert "| ...of those, rows whose pr_merged_at month is 2026-01 to 2026-06 | 2 |" in out  # Jan and 30 June only
    assert "| Distinct HIP numbers among the 2026-01 to 2026-06 rows | 2 |" in out  # HIP 5 merged on 1 July is out


def test_hips_range_excludes_hips_whose_only_merges_are_outside_it(derive):
    """A HIP merged only before or after the range is not counted, and a HIP merged in and out counts once."""
    out = _hips(derive, _evidence_doc(), start="2025-11", end="2025-11")
    assert "| Distinct HIP numbers among the 2025-11 to 2025-11 rows | 1 |" in out  # HIP 1's earlier PR
    out = _hips(derive, _evidence_doc(), start="2026-07", end="2026-07")
    assert "| Distinct HIP numbers among the 2026-07 to 2026-07 rows | 1 |" in out  # HIP 5 only


def test_hips_range_derived_line_names_range_and_field(derive):
    """The Derived line states the range, the date field used, and the row counts."""
    derived = _last(_hips(derive, _evidence_doc(), start="2026-01", end="2026-06"))
    assert derived.startswith("Derived: 2 distinct HIP numbers have at least one row with counted = true")
    assert "whose pr_merged_at month is 2026-01 to 2026-06 inclusive" in derived
    assert "(2 such rows of 4 counted merged rows, 7 rows in all)" in derived


def test_hips_range_notes_that_a_hip_is_not_first_implemented_in_the_range(derive):
    """The scoped count includes HIPs with earlier evidence, and the output says so."""
    out = _hips(derive, _evidence_doc(), start="2026-01", end="2026-06")
    assert any("not 'first implemented in the range'" in line for line in out)


def test_hips_range_leaves_the_funnel_comparison_unscoped_and_says_so(derive):
    """With a range, the funnel is compared with the any-merge-date count, and the output explains why."""
    out = _hips(derive, _evidence_doc(), _funnel_doc(evidence_all=2), start="2026-01", end="2026-06")
    assert "| Distinct HIP numbers among the 2026-01 to 2026-06 rows | 2 |" in out
    assert "| Distinct HIP numbers among all counted merged rows, any merge date | 3 |" in out
    assert "| Difference (evidence minus funnel), any merge date | 1 |" in out
    assert any(line.startswith("Note: the funnel comparison is unscoped. The funnel is cohort-based") for line in out)
    assert "the funnel comparison is unscoped because the funnel is cohort-based, not period-based" in _last(out)
    assert "3 HIPs across all merge dates against the funnel's" in _last(out)


def test_hips_range_board_check_uses_all_merge_dates(derive):
    """The Deferred HIP merged after the range is still named, because the funnel comparison is unscoped."""
    out = _hips(
        derive, _evidence_doc(), _funnel_doc(evidence_all=2), board=_board_doc(), start="2026-01", end="2026-06"
    )
    assert any("HIP-5 (Deferred)" in line and "equal to the difference" in line for line in out)


def test_hips_range_excludes_and_reports_rows_without_a_merge_date(derive):
    """A counted merged row with no readable pr_merged_at cannot be placed in a month, so it is excluded and reported."""
    doc = _evidence_doc()
    doc["rows"].append({"hip": 9, "pr_state": "MERGED", "counted": True, "pr_merged_at": None})
    out = _hips(derive, doc, start="2026-01", end="2026-06")
    assert any(line.startswith("Warning: 1 counted merged rows have no readable pr_merged_at") for line in out)
    assert "| Distinct HIP numbers among the 2026-01 to 2026-06 rows | 2 |" in out
    assert "1 counted merged rows have no readable pr_merged_at" in _last(out)


def test_hips_range_warns_when_to_is_the_generation_month(derive):
    """A range ending in the month the document was generated is a partial month and is flagged."""
    out = _hips(derive, _evidence_doc(), start="2026-01", end="2026-10")
    assert any(line.startswith("Warning: --to 2026-10 is the month the document was generated") for line in out)
    assert not any(
        line.startswith("Warning") for line in _hips(derive, _evidence_doc(), start="2026-01", end="2026-06")
    )


def test_hips_range_needs_the_merge_date_column(derive):
    """Scoping by month fails clearly when the rows have no pr_merged_at column."""
    doc = {"id": "x", "rows": [{"hip": 1, "pr_state": "MERGED", "counted": True}]}
    with pytest.raises(derive.DeriveError, match="no 'pr_merged_at' column"):
        _hips(derive, doc, start="2026-01", end="2026-06")
    assert _hips(derive, doc)  # unscoped needs no date


# --- single-employer ------------------------------------------------------


def test_single_employer_repos_reading_versus_chart_approximation(derive):
    """Repos give the table reading (distinct_orgs == 1) and the independent/unknown-free reading."""
    out = derive.single_employer_report(_repo_diversity_doc(), "repodiversity.json")
    assert "| distinct_orgs == 1 (the table's reading) | 4 |" in out
    assert "| distinct_orgs == 1 and independent == 0 and unknown == 0 (approximates the dashboard chart) | 2 |" in out
    assert "Columns used for the second reading: distinct_orgs, independent, unknown." in out
    assert "4 rows have distinct_orgs == 1 in repodiversity" in _last(out)
    assert "2 of them also satisfy distinct_orgs == 1 and independent == 0 and unknown == 0" in _last(out)


def test_single_employer_teams_use_the_single_employer_flag(derive):
    """Teams have no independent column, so the document's own single_employer flag is the second reading."""
    out = derive.single_employer_report(_team_diversity_doc(), "teamdiversity.json")
    assert "| distinct_orgs == 1 (the table's reading) | 3 |" in out
    assert "| distinct_orgs == 1 and single_employer is true (approximates the dashboard chart) | 2 |" in out
    assert any("no independent column" in line for line in out)


def test_single_employer_without_either_reading_warns(derive):
    """A document with neither the independent/unknown columns nor a flag gets only the table reading and a warning."""
    doc = {"id": "x", "rows": [{"distinct_orgs": 1}, {"distinct_orgs": 2}]}
    out = derive.single_employer_report(doc, "x.json")
    assert any(line.startswith("Warning: no independent/unknown columns") for line in out)
    assert _last(out) == "Derived: 1 rows have distinct_orgs == 1 in x."


def test_single_employer_rejects_other_documents(derive):
    """A document without distinct_orgs is refused."""
    with pytest.raises(derive.DeriveError, match="no 'distinct_orgs' column"):
        derive.single_employer_report({"rows": [{"repo": "a"}]}, "x.json")


# --- shared behaviour and the command line --------------------------------


def test_stale_document_is_called_out(derive):
    """A document that says stale: true gets a note beside its figures."""
    doc = _section_doc()
    doc["stale"] = True
    out = derive.period_report(doc, "s.json", "all", [])
    assert any(line.startswith("Note: understaffed says stale: true") for line in out)


def test_table_helper_escapes_pipes_and_aligns_numbers(derive):
    """Pipes in a cell are escaped and right-aligned columns get the markdown alignment marker."""
    assert derive._table(["A", "N"], [["x|y", 3]], right=(1,)) == ["| A | N |", "|---|---:|", "| x\\|y | 3 |"]


def test_month_range_crosses_a_year_boundary_and_rejects_reversed_input(derive):
    """Month ranges roll over December and refuse a --from after --to."""
    assert derive._month_range("2025-11", "2026-02") == ["2025-11", "2025-12", "2026-01", "2026-02"]
    with pytest.raises(derive.DeriveError):
        derive._month_range("2026-02", "2026-01")


@pytest.mark.parametrize(
    "command",
    ["releases", "months", "period", "hips", "single-employer"],
)
def test_main_prints_a_table_and_ends_with_a_derived_line(derive, tmp_path: Path, capsys, command):
    """Every subcommand exits 0, prints a markdown table, and its last line starts with Derived:."""
    docs = {
        "releases": (_release_doc(), ["--from", "2026-01", "--to", "2026-02"]),
        "months": (_monthly_doc(), ["--from", "2026-01", "--to", "2026-03", "--compare", "2025-12,2026-01"]),
        "period": (_section_doc(), ["--period", "30d", "--where", "maintainers=<=2"]),
        "hips": (_evidence_doc(), []),
        "single-employer": (_repo_diversity_doc(), []),
    }
    doc, extra = docs[command]
    path = _write(tmp_path, f"{command}.json", doc)
    assert derive.main([command, path, *extra]) == 0
    lines = capsys.readouterr().out.rstrip("\n").split("\n")
    assert lines[0].startswith("| ") and lines[1].startswith("|---")
    assert lines[-1].startswith("Derived: ")
    assert sum(1 for line in lines if line.startswith("Derived:")) == 1


def test_main_hips_with_funnel_and_board(derive, tmp_path: Path, capsys):
    """The hips command loads the funnel and the board from their paths."""
    evidence = _write(tmp_path, "e.json", _evidence_doc())
    funnel = _write(tmp_path, "f.json", _funnel_doc(evidence_all=2))
    board = _write(tmp_path, "b.json", _board_doc())
    assert derive.main(["hips", evidence, "--funnel", funnel, "--board", board]) == 0
    out = capsys.readouterr().out
    assert "| Difference (evidence minus funnel) | 1 |" in out
    assert "HIP-5 (Deferred)" in out


def test_main_board_without_funnel_is_an_error(derive, tmp_path: Path, capsys):
    """--board explains the gap to the funnel, so it is refused alone."""
    evidence = _write(tmp_path, "e.json", _evidence_doc())
    board = _write(tmp_path, "b.json", _board_doc())
    assert derive.main(["hips", evidence, "--board", board]) == 2
    assert "needs --funnel" in capsys.readouterr().err


def test_main_reports_unreadable_and_invalid_files(derive, tmp_path: Path, capsys):
    """A missing file or invalid JSON exits 2 with an error line and prints no table."""
    assert derive.main(["period", str(tmp_path / "missing.json")]) == 2
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert derive.main(["period", str(bad)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cannot read" in captured.err and "not valid JSON" in captured.err


def test_main_rejects_a_malformed_month(derive, tmp_path: Path, capsys):
    """A month that is not YYYY-MM is rejected by the argument parser."""
    path = _write(tmp_path, "r.json", _release_doc())
    with pytest.raises(SystemExit) as exc:
        derive.main(["releases", path, "--from", "2026-13", "--to", "2026-02"])
    assert exc.value.code == 2
    assert "not a month in YYYY-MM form" in capsys.readouterr().err


def test_main_hips_with_a_range_and_the_funnel(derive, tmp_path: Path, capsys):
    """The hips command takes --from and --to together with the funnel and prints the unscoped note."""
    evidence = _write(tmp_path, "e.json", _evidence_doc())
    funnel = _write(tmp_path, "f.json", _funnel_doc(evidence_all=2))
    assert derive.main(["hips", evidence, "--funnel", funnel, "--from", "2026-01", "--to", "2026-06"]) == 0
    out = capsys.readouterr().out
    assert "| Distinct HIP numbers among the 2026-01 to 2026-06 rows | 2 |" in out
    assert "the funnel comparison is unscoped" in out


def test_main_hips_range_needs_both_ends_in_order(derive, tmp_path: Path, capsys):
    """--from without --to, or a reversed range, exits 2 with an error."""
    evidence = _write(tmp_path, "e.json", _evidence_doc())
    assert derive.main(["hips", evidence, "--from", "2026-01"]) == 2
    assert "--from and --to go together" in capsys.readouterr().err
    assert derive.main(["hips", evidence, "--from", "2026-06", "--to", "2026-01"]) == 2
    assert "is after --to" in capsys.readouterr().err
