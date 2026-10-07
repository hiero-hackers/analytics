"""Tests for the lfdt-report skill's inventory script (fetch, show, doc, sources and tac).

Everything runs on a small synthetic manifest and small HTML snippets written to ``tmp_path``.
The fetches exercised end to end use ``file://`` URLs, so no test touches the network.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "lfdt-report" / "scripts"
DASH = "https://hiero-hackers.github.io/analytics/#"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def inv():
    """Load inventory.py from the skill directory."""
    return _load("inventory")


def _write(root: Path, rel: str, doc: dict) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _timeseries(doc_id: str, frequency: str, buckets: list[str], comparison: dict | None, generated_at: str | None):
    doc = {
        "id": doc_id,
        "kind": "timeseries",
        "frequency": frequency,
        "comparison": comparison,
        "top_n": None,
        "window": {"kind": "calendar", "first": buckets[0], "last": buckets[-1]},
        "rows": [{"bucket": b, "a": i, "partial": i == len(buckets) - 1} for i, b in enumerate(buckets)],
        "stale": False,
    }
    if generated_at:
        doc["generated_at"] = generated_at
    return doc


def _variant(label: str, kind: str, path: str, **extra) -> dict:
    return {"label": label, "interactive": {"kind": kind, "path": path}, **extra}


MANIFEST = {
    "version": "v1",
    "wip": True,
    "generated_at": "2026-10-06T09:15:42+00:00",
    "provenance": {"git_sha": "abc1234", "data_as_of": "2026-10-05T23:30:00+00:00"},
    "macro_order": ["Contributors", "Governance", "Security & scorecards", "Releases", "Community"],
    "macro_absent_notes": {
        "Community": "Discord is published once, under acme.",
        "Releases": "No releases pipeline data for this org yet.",
    },
    "orgs": {
        "acme": {
            "sections": [
                {
                    "id": "profiles",
                    "macro": "Contributors",
                    "title": "All contributors",
                    "row_count": 3,
                    "path": "acme/profiles.json",
                },
                {
                    "id": "members",
                    "macro": "Governance",
                    "title": "Members",
                    "row_count": 2,
                    "path": "acme/members.json",
                },
                {
                    "id": "committers",
                    "macro": "Governance",
                    "title": "Committers",
                    "row_count": 1,
                    "path": "acme/committers.json",
                    "absorbed_by": "members",
                },
                {
                    "id": "codeowners",
                    "macro": "Security & scorecards",
                    "title": "CODEOWNERS",
                    "row_count": 2,
                    "path": "acme/codeowners.json",
                },
            ],
            "chart_sections": [
                {
                    "id": "pipeline",
                    "macro": "Governance",
                    "title": "Pipeline",
                    "description": "",
                    "charts": [
                        {
                            "title": "Active people",
                            "methodology": ["Chart-level step."],
                            "variants": [
                                _variant(
                                    "All time", "timeseries", "acme/charts/pipeline_yearly.json", note="Yearly note."
                                ),
                                _variant(
                                    "1 year",
                                    "timeseries",
                                    "acme/charts/pipeline_monthly.json",
                                    note="Monthly note from the manifest variant.",
                                ),
                            ],
                        },
                    ],
                },
                {
                    "id": "heat",
                    "macro": "Contributors",
                    "title": "Heat",
                    "description": "",
                    "charts": [
                        {"title": "By person", "variants": [_variant("By person", "matrix", "acme/charts/heat.json")]},
                    ],
                },
            ],
            "views": [
                {"id": "board", "macro": "Governance", "kind": "board", "title": "Board", "path": "acme/board.json"},
            ],
            "metrics": {
                "Contributors": [{"label": "contributors", "value": 3}],
                "Governance": [{"label": "maintainers", "value": "2"}, {"label": "known %", "value": "99%"}],
            },
            "entities": {"repositories": {"path": "acme/entities/repositories.json", "count": 4}},
        },
        "solo": {"sections": [], "chart_sections": [], "views": [], "metrics": {}},
    },
}


@pytest.fixture
def work(tmp_path: Path) -> Path:
    """Write the synthetic manifest and its documents into a work directory."""
    root = tmp_path / "work"
    _write(root, "manifest.json", MANIFEST)
    _write(
        root,
        "acme/profiles.json",
        {
            "id": "profiles",
            "title": "All contributors",
            "group": "People",
            "description": "One row per person with any tracked activity.",
            "columns": [{"key": "login", "label": "GitHub login"}, {"key": "prs", "label": "PRs opened"}],
            "rows": [{"login": "a"}, {"login": "b"}, {"login": "c"}],
            "row_count": 3,
            "periods": {"7d": [{"login": "a"}], "30d": [{"login": "a"}, {"login": "b"}], "365d": [{}, {}, {}]},
            "generated_at": "2026-10-06T09:12:03+00:00",
            "stale": False,
        },
    )
    _write(
        root,
        "acme/members.json",
        {"id": "members", "rows": [{}, {}], "row_count": 2, "stale": True, "generated_at": "2026-10-04T01:00:00+00:00"},
    )
    _write(root, "acme/committers.json", {"id": "committers", "rows": [{}], "row_count": 1})
    _write(root, "acme/codeowners.json", {"id": "codeowners", "rows": [{}, {}], "row_count": 2, "stale": False})
    yearly = _timeseries(
        "pipeline_yearly",
        "year",
        ["2024", "2025", "2026"],
        {"current": "2025", "previous": "2024"},
        "2026-10-06T09:08:12+00:00",
    )
    yearly.update(
        {
            "note": "Yearly note.",
            "methodology": ["Count people."],
            "population": "People active in the year.",
            "metric": "active_people",
            "unit": "People",
            "series": [{"key": "a", "label": "Alpha"}, {"key": "b", "label": "Beta"}],
        }
    )
    _write(root, "acme/charts/pipeline_yearly.json", yearly)
    # No generated_at: the as-of date must come from the manifest's provenance.
    _write(
        root,
        "acme/charts/pipeline_monthly.json",
        _timeseries("pipeline_monthly", "month", ["2026-08", "2026-09", "2026-10"], None, None),
    )
    _write(
        root,
        "acme/charts/heat.json",
        {
            "id": "heat",
            "kind": "matrix",
            "top_n": 25,
            "window": {"kind": "trailing", "days": 183, "end": "2026-10-06T09:00:00+00:00"},
            "rows": [{"k": i} for i in range(30)],
            "generated_at": "2026-10-06T09:12:32+00:00",
            "stale": False,
        },
    )
    _write(root, "acme/board.json", {"id": "board", "kind": "board", "generated_at": "2026-10-06T09:14:32+00:00"})
    return root


def test_collect_paths_lists_every_document_reference_once(inv):
    """Sections, chart variants, views and entity indexes are all collected, in order, without repeats."""
    entry = json.loads(json.dumps(MANIFEST["orgs"]["acme"]))
    entry["chart_sections"][1]["charts"][0]["variants"].append(_variant("Again", "matrix", "acme/charts/heat.json"))
    entry["entities"]["contributors"] = {"path": "acme/entities/contributors.json", "count": 9}
    assert inv.collect_paths(entry) == [
        "acme/profiles.json",
        "acme/members.json",
        "acme/committers.json",
        "acme/codeowners.json",
        "acme/charts/pipeline_yearly.json",
        "acme/charts/pipeline_monthly.json",
        "acme/charts/heat.json",
        "acme/board.json",
        "acme/entities/repositories.json",
        "acme/entities/contributors.json",
    ]


def test_collect_paths_tolerates_a_sparse_org(inv):
    """An org with no views, charts or entities (and missing keys) yields only what it has."""
    assert inv.collect_paths({}) == []
    sparse = {"sections": [{"id": "s", "path": "x/s.json"}], "entities": {"repositories": {"count": 0}}}
    assert inv.collect_paths(sparse) == ["x/s.json"]


def test_show_sections_table_has_period_counts_and_flags(inv, work, capsys):
    """Each section row carries all-time rows, per-period list lengths, absorbed_by, stale and generated."""
    assert inv.main(["show", "acme", "--work", str(work)]) == 0
    out = capsys.readouterr().out
    assert "| profiles | Contributors | All contributors | 3 | 7d=1 30d=2 365d=3 | - | no | 2026-10-06 09:12Z |" in out
    assert "| members | Governance | Members | 2 | - | - | yes | 2026-10-04 01:00Z |" in out
    assert "| committers | Governance | Committers | 1 | - | members | - | - |" in out


def test_show_lists_absent_macros_with_their_note(inv, work, capsys):
    """Macros in macro_order the org lacks are marked absent and carry the manifest's note."""
    inv.main(["show", "acme", "--work", str(work)])
    out = capsys.readouterr().out
    assert "| Community | absent | 0 | 0 | 0 | 0 | Discord is published once, under acme. |" in out
    assert "| Releases | absent | 0 | 0 | 0 | 0 | No releases pipeline data for this org yet. |" in out
    assert "| Governance | present | 2 | 1 | 1 | 2 | - |" in out
    assert "| Security & scorecards | present | 1 | 0 | 0 | 0 | - |" in out


def test_show_chart_rows_report_frequency_partial_buckets_and_comparison(inv, work, capsys):
    """Timeseries variants show their frequency range, partial bucket and comparison pair; others a window."""
    inv.main(["show", "acme", "--work", str(work)])
    out = capsys.readouterr().out
    yearly = (
        "| pipeline | Governance | Active people | All time | pipeline_yearly | timeseries | year (2024..2026) "
        "| 3 | 2026 | 2025 vs 2024 | - | no |"
    )
    monthly = (
        "| pipeline | Governance | Active people | 1 year | pipeline_monthly | timeseries "
        "| month (2026-08..2026-10) | 3 | 2026-10 | - | - | no |"
    )
    heat = (
        "| heat | Contributors | By person | By person | heat | matrix | trailing 183d to 2026-10-06 "
        "| 30 | - | - | 25 | no |"
    )
    assert yearly in out
    assert monthly in out
    assert heat in out


def test_show_prints_views_tiles_and_entity_counts(inv, work, capsys):
    """Views, tiles and entity counts each get their own table; a missing index shows dashes."""
    inv.main(["show", "acme", "--work", str(work)])
    out = capsys.readouterr().out
    assert "| board | Governance | board |" in out
    assert "| Governance | known % | 99% |" in out
    assert "| repositories | 4 | acme/entities/repositories.json |" in out
    assert "| contributors | - | - |" in out
    assert "wip=true" in out


def test_show_json_matches_the_markdown_content(inv, work, capsys):
    """--json emits the same inventory as one object, with raw counts and partial bucket names."""
    assert inv.main(["show", "acme", "--work", str(work), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["org"] == "acme"
    assert data["provenance"]["git_sha"] == "abc1234"
    profiles = next(s for s in data["sections"] if s["id"] == "profiles")
    assert profiles["periods"] == {"7d": 1, "30d": 2, "365d": 3}
    yearly = next(c for c in data["charts"] if c["document_id"] == "pipeline_yearly")
    assert yearly["partial"] == ["2026"]
    assert yearly["comparison"] == {"current": "2025", "previous": "2024"}
    assert {m["macro"] for m in data["macros"] if not m["present"]} == {"Releases", "Community"}
    assert len(data["tiles"]) == 3


def test_show_unknown_org_exits_2_and_lists_orgs(inv, work, capsys):
    """An org that is not in the manifest is a bad-input exit, naming the orgs that exist."""
    with pytest.raises(SystemExit) as exc:
        inv.main(["show", "nope", "--work", str(work)])
    assert exc.value.code == 2
    assert "acme, solo" in capsys.readouterr().err


def test_show_without_a_fetch_exits_2_with_a_hint(inv, tmp_path, capsys):
    """An empty work directory tells the user to run fetch first."""
    with pytest.raises(SystemExit) as exc:
        inv.main(["show", "acme", "--work", str(tmp_path / "empty")])
    assert exc.value.code == 2
    assert "fetch" in capsys.readouterr().err


def test_sources_section_line_shape(inv, work, capsys):
    """A section entry names the kind, id, as-of date, BASE path and dashboard link, on one line."""
    assert inv.main(["sources", "acme", "profiles", "--work", str(work)]) == 0
    assert capsys.readouterr().out == (
        "[1] Section profiles; data as of 2026-10-06. JSON: BASE/acme/profiles.json. "
        f"Dashboard: {DASH}tab=Contributors&org=acme&widget=profiles\n"
    )


def test_sources_chart_document_id_cites_the_card_and_variant(inv, work, capsys):
    """A chart document id is cited as its card, with the variant label and the document id in brackets."""
    assert inv.main(["sources", "acme", "pipeline_yearly", "--work", str(work), "--start", "7"]) == 0
    assert capsys.readouterr().out == (
        "[7] Chart pipeline, All time variant (pipeline_yearly); data as of 2026-10-06. "
        "JSON: BASE/acme/charts/pipeline_yearly.json. "
        f"Dashboard: {DASH}tab=Governance&org=acme&widget=pipeline\n"
    )


def test_sources_card_id_emits_every_variant_and_dedupes(inv, work, capsys):
    """A card id yields one numbered entry per variant; citing a variant's document afterwards adds nothing."""
    assert inv.main(["sources", "acme", "pipeline", "pipeline_monthly", "--work", str(work)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("[1] Chart pipeline, All time variant (pipeline_yearly); data as of 2026-10-06.")
    # pipeline_monthly has no generated_at, so the manifest's data_as_of date is used.
    assert lines[1].startswith("[2] Chart pipeline, 1 year variant (pipeline_monthly); data as of 2026-10-05.")


def test_sources_tile_gives_value_manifest_path_and_tab_link(inv, work, capsys):
    """A tile has no document or widget: the entry shows its value and points at the manifest and the tab."""
    assert inv.main(["sources", "acme", "tile:Governance/known %", "--work", str(work)]) == 0
    assert capsys.readouterr().out == (
        "[1] Tile Governance/known % (99%); data as of 2026-10-05. JSON: BASE/manifest.json. "
        f"Dashboard: {DASH}tab=Governance&org=acme\n"
    )


def test_sources_view_and_url_encoded_macro(inv, work, capsys):
    """Views link by their id, and an ampersand in a macro name is URL-encoded in the tab."""
    assert inv.main(["sources", "acme", "board", "codeowners", "--work", str(work), "--base", "https://x/v1"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "[1] View board; data as of 2026-10-06. JSON: https://x/v1/acme/board.json." in lines[0]
    assert lines[1].endswith(f"Dashboard: {DASH}tab=Security%20%26%20scorecards&org=acme&widget=codeowners")
    assert "data as of 2026-10-05" in lines[1]  # no generated_at in the document: manifest fallback


def test_sources_unknown_id_warns_continues_and_exits_1(inv, work, capsys):
    """Unknown ids (including an unknown tile) warn on stderr; known ids are still printed and numbered."""
    code = inv.main(["sources", "acme", "profiles", "nonsense", "tile:Governance/nope", "members", "--work", str(work)])
    captured = capsys.readouterr()
    assert code == 1
    assert "unknown id 'nonsense'" in captured.err
    assert "unknown id 'tile:Governance/nope'" in captured.err
    lines = captured.out.splitlines()
    assert [line.split(" ")[0] for line in lines] == ["[1]", "[2]"]
    assert lines[1].startswith("[2] Section members;")


def test_sources_unknown_org_exits_2(inv, work):
    """The sources command checks the org before resolving ids."""
    with pytest.raises(SystemExit) as exc:
        inv.main(["sources", "nope", "profiles", "--work", str(work)])
    assert exc.value.code == 2


def test_fetch_downloads_then_skips_and_refreshes(inv, work, tmp_path, capsys):
    """Fetch copies the manifest and referenced documents (via file:// URLs), skips existing files, honours --refresh."""
    dest = tmp_path / "fetched"
    args = ["fetch", "acme", "--base", work.as_uri(), "--work", str(dest)]
    # Documents the manifest references but this synthetic API never published must fail loudly.
    with pytest.raises(SystemExit) as exc:
        inv.main(args)
    assert exc.value.code == 1
    assert "acme/entities/repositories.json" in capsys.readouterr().err
    _write(work, "acme/entities/repositories.json", {"rows": []})
    assert inv.main(args) == 0
    line = capsys.readouterr().out.strip()
    assert "version=v1 wip=true generated_at=2026-10-06T09:15:42+00:00 git_sha=abc1234" in line
    assert "data_as_of=2026-10-05T23:30:00+00:00" in line
    assert "skipped=" in line
    assert (dest / "acme" / "charts" / "pipeline_yearly.json").is_file()
    assert not list(dest.rglob("*.part"))
    assert inv.main(args) == 0
    assert "fetched=0 skipped=10" in capsys.readouterr().out
    assert inv.main([*args, "--refresh"]) == 0
    assert "fetched=10 skipped=0" in capsys.readouterr().out


def test_fetch_unknown_org_exits_2_with_the_org_list(inv, work, tmp_path, capsys):
    """An org that is not in the manifest exits 2 and names the orgs that are."""
    with pytest.raises(SystemExit) as exc:
        inv.main(["fetch", "nope", "--base", work.as_uri(), "--work", str(tmp_path / "w")])
    assert exc.value.code == 2
    assert "acme, solo" in capsys.readouterr().err


def test_fetch_refuses_paths_that_escape_the_work_directory(inv, tmp_path, capsys):
    """A manifest path with .. or a leading slash is rejected rather than written outside WORK."""
    with pytest.raises(SystemExit):
        inv._destination(tmp_path, "../evil.json")
    with pytest.raises(SystemExit):
        inv._destination(tmp_path, "/abs/evil.json")
    assert "refusing manifest path" in capsys.readouterr().err
    assert inv._destination(tmp_path, "acme/ok.json") == (tmp_path / "acme" / "ok.json").resolve()


# --------------------------------------------------------------------------
# sources: period tables, sorting, help
# --------------------------------------------------------------------------


def test_sources_period_table_entry_names_the_period_and_row_counts(inv, work, capsys):
    """ID@7d cites that period's table, with its row count beside the all-time count (singular for one row)."""
    assert inv.main(["sources", "acme", "profiles@365d", "profiles@7d", "profiles", "--work", str(work)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("[1] Section profiles, 365d period table (3 rows; 3 all time); data as of 2026-10-06.")
    assert lines[1].startswith("[2] Section profiles, 7d period table (1 row; 3 all time); data as of 2026-10-06.")
    assert lines[2].startswith("[3] Section profiles; data as of 2026-10-06.")
    assert all(line.endswith("widget=profiles") for line in lines)


def test_sources_period_table_that_does_not_exist_is_an_unknown_id(inv, work, capsys):
    """A period the document lacks, or a section that is not there, warns and exits 1 without an entry."""
    code = inv.main(["sources", "acme", "profiles@90d", "members@7d", "ghost@7d", "--work", str(work)])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "has no '90d' period table (it has: 7d, 30d, 365d)" in captured.err
    assert "has no '7d' period table (it has: none)" in captured.err
    assert "no section 'ghost'" in captured.err


def test_sources_sorted_orders_by_id_and_keeps_a_cards_variants_in_manifest_order(inv, work, capsys):
    """--sorted numbers entries by id, so cited order does not matter; without it they follow the arguments."""
    args = ["sources", "acme", "profiles", "pipeline_monthly", "board", "pipeline", "--work", str(work)]
    assert inv.main(args) == 0
    plain = [line.split(";")[0] for line in capsys.readouterr().out.splitlines()]
    assert plain[0] == "[1] Section profiles"
    assert inv.main([*args, "--sorted"]) == 0
    ordered = [line.split(";")[0] for line in capsys.readouterr().out.splitlines()]
    assert ordered == [
        "[1] View board",
        "[2] Chart pipeline, All time variant (pipeline_yearly)",
        "[3] Chart pipeline, 1 year variant (pipeline_monthly)",
        "[4] Section profiles",
    ]


def test_sources_help_documents_every_id_form_and_the_sorted_flag(inv, capsys):
    """--help lists the accepted id forms (section, card, chart document, view, tile, period) and --sorted."""
    with pytest.raises(SystemExit) as exc:
        inv.main(["sources", "--help"])
    assert exc.value.code == 0
    text = capsys.readouterr().out
    for fragment in ("a section id", "a card id", "chart document id", "a view id", "tile:<Macro>/<label>", "@365d"):
        assert fragment in text
    assert "--sorted" in text


# --------------------------------------------------------------------------
# doc
# --------------------------------------------------------------------------


def test_doc_section_prints_definitions_periods_and_columns(inv, work, capsys):
    """A section block carries title, kind, stale, description, row and period counts and column keys and labels."""
    assert inv.main(["doc", "acme", "profiles@30d", "--work", str(work)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("### Section profiles, 30d period table\n")
    assert "- title: All contributors" in out
    assert "- kind: section, macro Contributors, group People" in out
    assert "- generated_at: 2026-10-06T09:12:03+00:00" in out
    assert "- stale: no" in out
    assert "- description: One row per person with any tracked activity." in out
    assert "- period table cited: 30d: 2 rows, 3 all time" in out
    assert "- period row counts: 7d=1 30d=2 365d=3" in out
    assert "  - login: GitHub login" in out
    assert "  - prs: PRs opened" in out


def test_doc_chart_says_which_level_each_note_and_methodology_came_from(inv, work, capsys):
    """Document, manifest variant and manifest chart levels are labelled; identical text is merged, a difference shown."""
    assert inv.main(["doc", "acme", "pipeline_yearly", "pipeline_monthly", "--work", str(work)]) == 0
    yearly, monthly = capsys.readouterr().out.split("\n\n### ")
    assert yearly.startswith("### Chart pipeline, All time variant (pipeline_yearly)")
    assert "- note [document + manifest variant]: Yearly note." in yearly
    assert "- methodology [document]:\n  - Count people." in yearly
    assert "- methodology [manifest chart; differs from the above]:\n  - Chart-level step." in yearly
    assert "- population: People active in the year." in yearly
    assert "- frequency: year" in yearly
    assert "- comparison: 2025 vs 2024" in yearly
    assert "- partial buckets: 2026" in yearly
    assert "- series: a (Alpha), b (Beta)" in yearly
    assert "- window: 2024..2026" in yearly
    # The monthly document carries no note or methodology of its own.
    assert "- note [manifest variant]: Monthly note from the manifest variant." in monthly
    assert "- methodology [manifest chart]:\n  - Chart-level step." in monthly
    assert "- comparison: none" in monthly
    assert "- generated_at" not in monthly


def test_doc_chart_without_any_note_says_none_rather_than_staying_silent(inv, work, capsys):
    """A chart with no note or methodology at any level says so, naming the three levels."""
    assert inv.main(["doc", "acme", "heat", "--work", str(work)]) == 0
    out = capsys.readouterr().out
    assert "- note: none at any level (document, manifest variant, manifest chart)" in out
    assert "- methodology: none at any level (document, manifest variant, manifest chart)" in out
    assert "- window: trailing 183d to 2026-10-06" in out
    assert "- top_n: 25" in out
    assert "- rows: 30 in the document" in out


def test_doc_card_id_prints_one_block_per_variant_and_view_and_tile_blocks(inv, work, capsys):
    """A card yields a block per variant; a view and a tile each get theirs, and blocks are ### headed."""
    assert inv.main(["doc", "acme", "pipeline", "board", "tile:Governance/known %", "--work", str(work)]) == 0
    out = capsys.readouterr().out
    headings = [line for line in out.splitlines() if line.startswith("### ")]
    assert headings == [
        "### Chart pipeline, All time variant (pipeline_yearly)",
        "### Chart pipeline, 1 year variant (pipeline_monthly)",
        "### View board",
        "### Tile Governance/known % (99%)",
    ]
    assert "- kind: view (board), macro Governance" in out
    assert "- label: known %" in out
    assert "- value: 99%" in out
    assert "- note: none at any level (manifest tile)" in out


def test_doc_tile_prints_note_and_methodology_steps(inv, tmp_path, work, capsys):
    """A tile's note and methodology steps come from the manifest entry, steps as a bullet list."""
    manifest = json.loads(json.dumps(MANIFEST))
    manifest["orgs"]["acme"]["metrics"]["Governance"][0].update(
        {"note": "Highest role only.", "methodology": ["a", "b"]}
    )
    _write(work, "manifest.json", manifest)
    assert inv.main(["doc", "acme", "tile:Governance/maintainers", "--work", str(work)]) == 0
    out = capsys.readouterr().out
    assert "### Tile Governance/maintainers (2)" in out
    assert "- note [manifest tile]: Highest role only." in out
    assert "- methodology [manifest tile]:\n  - a\n  - b" in out


def _wide_members_doc() -> dict:
    """Build a section document with a huge description, 50 columns, 100 methodology steps and marker rows."""
    return {
        "id": "members",
        "title": "Members",
        "description": "word " * 500,
        "columns": [{"key": f"col{i}", "label": f"Column {i}"} for i in range(50)],
        "rows": [{"login": "SECRET-ROW-VALUE"}] * 3,
        "row_count": 3,
        "methodology": [f"step {i}" for i in range(100)],
    }


def test_doc_clips_long_fields_and_never_prints_rows(inv, work, capsys):
    """Long text, a long column list and a long methodology are each cut, and rows never appear."""
    _write(work, "acme/members.json", _wide_members_doc())
    assert inv.main(["doc", "acme", "members", "--work", str(work)]) == 0
    out = capsys.readouterr().out
    assert "SECRET-ROW-VALUE" not in out
    assert "(clipped, 2499 characters)" in out
    assert "  - step 11" in out and "  - step 12" not in out
    assert "... and 88 more steps" in out
    assert "  - col19: Column 19" in out and "col20" not in out
    assert "... and 30 more" in out
    assert len(out.splitlines()) <= inv.MAX_DOC_LINES


def test_doc_block_is_hard_capped_at_the_line_limit(inv, work, capsys, monkeypatch):
    """Whatever the fields hold, a block never exceeds MAX_DOC_LINES lines and says what it clipped."""
    monkeypatch.setattr(inv, "MAX_DOC_LINES", 12)
    _write(work, "acme/members.json", _wide_members_doc())
    assert inv.main(["doc", "acme", "members", "--work", str(work)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) <= 12 + 2  # the heading and its blank line sit outside the cap
    assert lines[-1].startswith("- ... ") and lines[-1].endswith("more lines clipped")


def test_doc_unknown_id_warns_continues_and_exits_1(inv, work, capsys):
    """Unknown ids warn on stderr; known ids are still described and the exit code is 1."""
    code = inv.main(["doc", "acme", "nonsense", "profiles", "--work", str(work)])
    captured = capsys.readouterr()
    assert code == 1
    assert "unknown id 'nonsense'" in captured.err
    assert "### Section profiles" in captured.out


# --------------------------------------------------------------------------
# tac
# --------------------------------------------------------------------------


def _instructions_html(title: str, naming: str, with_questions: bool = True) -> str:
    """Build a small mkdocs-like instruction page: chrome outside the article, content inside it."""
    questions = (
        "<p>The review should answer the following questions:</p>"
        "<ul><li>First question?</li><li><p>Second <a href='x'>question</a>?</p></li></ul>"
        if with_questions
        else "<p>Nothing to see.</p>"
    )
    return (
        "<!doctype html><html><head><title>t</title><script>var a = '<p>script text</p>';</script></head><body>"
        "<header><p>Site header</p></header><nav><ul><li>Nav item</li></ul></nav>"
        f"<article><h1 id='top'>{title}<a class='headerlink' href='#top'>&para;</a></h1>"
        f"<p>Create a file in the <code>tac/project-updates</code> subdirectory and name the file <code>{naming}</code> "
        "(e.g., <code>2024/x.md</code>). Update the <code>mkdocs.yml</code> document.</p>"
        f"<h1>What should it contain</h1>{questions}"
        "<h1>What Does the TAC Evaluate</h1><p>Specifically:</p>"
        "<ul><li>Signs of activity.</li><li>Diversity of <a href='y'>maintainers</a>.</li></ul>"
        "<h1>What is the outcome</h1><ul><li>Not an evaluation bullet.</li></ul>"
        "</article><footer><p>Footer text</p></footer></body></html>"
    )


SCHEDULE_HTML = (
    "<html><body><article><h1>2026 Schedule</h1><p>NOTE: 1H is the annual review.</p><table>"
    "<thead><tr><th>Quarter</th><th>Date</th><th>Project</th></tr></thead><tbody>"
    "<tr><td>2H</td><td>2026-09-03</td><td>Hiero</td></tr>"
    "<tr><td>1H (annual)</td><td>2026-03-05</td><td>Hiero</td></tr>"
    "<tr><td>1H (annual)</td><td>2026-03-05</td><td>Hieroglyph</td></tr>"
    "<tr><td>2H</td><td>2026-08-13</td><td>Cacti</td></tr>"
    "</tbody></table></article></body></html>"
)


def _tac_site(root: Path, schedule: bool = True, instructions: bool = True) -> Path:
    """Write a fake project-updates site (instruction pages and a 2026 schedule) under ``root``."""
    site = root / "site"
    pages = {
        "annual-review-instructions": _instructions_html("Annual Review Instructions", "YYYY-annual-Project-Name.md"),
        "mid-year-update-instructions": _instructions_html("Mid-year Instructions", "YYYY-MidYear-Project-Name.md"),
    }
    for slug, page in pages.items():
        if instructions:
            (site / slug).mkdir(parents=True, exist_ok=True)
            (site / slug / "index.html").write_text(page, encoding="utf-8")
    if schedule:
        (site / "2026" / "2026-schedule").mkdir(parents=True, exist_ok=True)
        (site / "2026" / "2026-schedule" / "index.html").write_text(SCHEDULE_HTML, encoding="utf-8")
    return site


def test_html_to_blocks_keeps_only_article_text_without_chrome_or_permalinks(inv):
    """Scripts, header, nav and footer are dropped, the pilcrow permalink goes, code is backticked, list items kept."""
    blocks = inv.html_to_blocks(_instructions_html("Annual Review Instructions", "YYYY-annual-Project-Name.md"))
    text = inv.blocks_to_text(blocks)
    assert "script text" not in text and "Site header" not in text and "Nav item" not in text
    assert "Footer text" not in text
    assert "¶" not in text
    assert "# Annual Review Instructions" in text
    assert "name the file `YYYY-annual-Project-Name.md`" in text
    assert "- Second question?" in text  # a paragraph inside a list item stays in the item
    assert [b["text"] for b in blocks if b["kind"] == "li"][:2] == ["First question?", "Second question?"]


def test_tac_extractors_find_questions_evaluation_and_naming_sentence(inv):
    """The question list, the evaluation bullets (up to the next heading) and the naming sentence are found."""
    blocks = inv.html_to_blocks(_instructions_html("A", "YYYY-annual-Project-Name.md"))
    assert inv.questions_of(blocks) == ["First question?", "Second question?"]
    assert inv.evaluation_of(blocks) == ["Signs of activity.", "Diversity of maintainers."]
    assert inv.naming_sentence_of(blocks) == (
        "Create a file in the `tac/project-updates` subdirectory and name the file `YYYY-annual-Project-Name.md` "
        "(e.g., `2024/x.md`)."
    )
    empty = inv.html_to_blocks("<article><p>Nothing here.</p></article>")
    assert inv.questions_of(empty) == [] and inv.evaluation_of(empty) == [] and inv.naming_sentence_of(empty) is None


def test_schedule_rows_match_the_project_as_a_word_sort_by_date_and_gloss_the_report(inv):
    """Only rows naming the project as a whole word match; they are date-ordered and 1H/2H are glossed."""
    rows = inv.schedule_rows(inv.html_to_blocks(SCHEDULE_HTML), "Hiero")
    assert [(r["date"], r["label"], r["report"]) for r in rows] == [
        ("2026-03-05", "1H (annual)", "annual review"),
        ("2026-09-03", "2H", "mid-year update"),
    ]
    assert inv.schedule_rows(inv.html_to_blocks(SCHEDULE_HTML), "Nobody") == []


def test_tac_prints_numbered_questions_evaluation_naming_and_schedule_and_saves_text(inv, tmp_path, capsys):
    """The tac command prints both reports' numbered questions and evaluation bullets, the naming lines and the schedule rows."""
    site = _tac_site(tmp_path)
    work = tmp_path / "w"
    assert inv.main(["tac", "--year", "2026", "--site", site.as_uri(), "--work", str(work)]) == 0
    out = capsys.readouterr().out
    assert "## Annual review: the report should answer" in out
    assert "1. First question?\n2. Second question?" in out
    assert "## Mid-year update: what the TAC evaluates" in out
    assert "- Signs of activity.\n- Diversity of maintainers." in out
    assert "- Annual review: Create a file" in out and "`YYYY-annual-Project-Name.md`" in out
    assert "`YYYY-MidYear-Project-Name.md`" in out
    assert "- 2026-03-05: annual review (schedule says '1H (annual)')" in out
    assert "- 2026-09-03: mid-year update (schedule says '2H')" in out
    assert "Cacti" not in out
    saved = sorted(path.name for path in (work / "tac").iterdir())
    assert saved == ["2026-schedule.txt", "annual-review-instructions.txt", "mid-year-update-instructions.txt"]
    assert "Quarter | Date | Project" in (work / "tac" / "2026-schedule.txt").read_text(encoding="utf-8")


def test_tac_falls_back_to_the_directory_listing_when_the_year_has_no_schedule(inv, tmp_path, capsys):
    """With no schedule page, tac lists the project's files from the contents API and says it fell back."""
    site = _tac_site(tmp_path, schedule=False)
    api = tmp_path / "api"
    api.mkdir()
    (api / "2026").write_text(json.dumps([{"name": "2026-annual-Hiero.md"}, {"name": "2026-annual-Other.md"}]))
    work = tmp_path / "w"
    args = ["tac", "--year", "2026", "--site", site.as_uri(), "--api", api.as_uri(), "--work", str(work)]
    assert inv.main(args) == 0
    out = capsys.readouterr().out
    assert "No schedule page exists for 2026" in out
    assert "Fell back to the directory listing" in out
    assert "- 2026-annual-Hiero.md" in out
    assert "Other" not in out
    assert (work / "tac" / "2026-listing.txt").read_text(encoding="utf-8").splitlines() == [
        "2026-annual-Hiero.md",
        "2026-annual-Other.md",
    ]


def test_tac_schedule_failure_still_prints_instructions_but_exits_1(inv, tmp_path, capsys):
    """When neither the schedule page nor the listing exists, the instructions print and the exit code is 1."""
    site = _tac_site(tmp_path, schedule=False)
    args = ["tac", "--year", "2026", "--site", site.as_uri(), "--api", (tmp_path / "none").as_uri()]
    assert inv.main([*args, "--work", str(tmp_path / "w")]) == 1
    captured = capsys.readouterr()
    assert "1. First question?" in captured.out
    assert "NOT AVAILABLE: no schedule page for 2026" in captured.out
    assert "Missing: schedule:" in captured.err


def test_tac_missing_instruction_page_fails_loudly_naming_the_url(inv, tmp_path, capsys):
    """A missing instruction page is a hard failure that names the URL."""
    site = _tac_site(tmp_path, instructions=False)
    with pytest.raises(SystemExit) as exc:
        inv.main(["tac", "--year", "2026", "--site", site.as_uri(), "--work", str(tmp_path / "w")])
    assert exc.value.code == 1
    assert "annual-review-instructions" in capsys.readouterr().err


def test_tac_reports_a_page_whose_layout_no_longer_has_the_questions(inv, tmp_path, capsys):
    """A page without the expected question list is named on stderr and the exit code is 1."""
    site = _tac_site(tmp_path)
    page = _instructions_html("Annual Review Instructions", "YYYY-annual-Project-Name.md", with_questions=False)
    (site / "annual-review-instructions" / "index.html").write_text(page, encoding="utf-8")
    assert inv.main(["tac", "--year", "2026", "--site", site.as_uri(), "--work", str(tmp_path / "w")]) == 1
    assert "Missing: Annual review: questions" in capsys.readouterr().err
