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
