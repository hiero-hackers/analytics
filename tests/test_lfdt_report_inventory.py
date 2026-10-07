"""Tests for the lfdt-report skill's inventory script (fetch path list, show tables, sources lines).

Everything runs on a small synthetic manifest written to ``tmp_path``. The only fetch exercised
end to end uses ``file://`` URLs, so no test touches the network.
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


def _variant(label: str, kind: str, path: str) -> dict:
    return {"label": label, "interactive": {"kind": kind, "path": path}}


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
                            "variants": [
                                _variant("All time", "timeseries", "acme/charts/pipeline_yearly.json"),
                                _variant("1 year", "timeseries", "acme/charts/pipeline_monthly.json"),
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
    _write(
        root,
        "acme/charts/pipeline_yearly.json",
        _timeseries(
            "pipeline_yearly",
            "year",
            ["2024", "2025", "2026"],
            {"current": "2025", "previous": "2024"},
            "2026-10-06T09:08:12+00:00",
        ),
    )
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


def test_sources_tile_gives_manifest_path_and_tab_link(inv, work, capsys):
    """A tile has no document or widget: the entry points at the manifest and the tab."""
    assert inv.main(["sources", "acme", "tile:Governance/known %", "--work", str(work)]) == 0
    assert capsys.readouterr().out == (
        "[1] Tile Governance/known %; data as of 2026-10-05. JSON: BASE/manifest.json. "
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
