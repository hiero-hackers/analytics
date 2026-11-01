"""Tests for the lfdt-report draft checker."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "lfdt-report" / "scripts" / "check_draft.py"
_SPEC = importlib.util.spec_from_file_location("lfdt_check_draft", _PATH)
assert _SPEC and _SPEC.loader
check_draft = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check_draft)

GOOD = """[//]: # (SPDX-License-Identifier: CC-BY-4.0)

# 2026 Annual Review Hiero

Data as of 20 October 2026.

## Project Health

Hiero lists [42 repositories](https://hiero-hackers.github.io/analytics/#tab=Contributors&org=hiero-ledger&widget=repo-growth) [1].

## Appendix: Sources

[1] Repo growth, https://example.org/a
"""
MANIFEST = {"orgs": {"hiero-ledger": {"sections": [], "chart_sections": [{"id": "repo-growth"}], "views": []}}}


def test_clean_draft_passes() -> None:
    """A well-formed draft raises neither failures nor warnings."""
    assert check_draft.check(GOOD, MANIFEST) == ([], [])


def test_missing_spdx_and_data_as_of_fail() -> None:
    """A missing SPDX line and a missing data-as-of date each fail."""
    text = GOOD.replace("[//]: # (SPDX-License-Identifier: CC-BY-4.0)", "# x").replace("Data as of", "Taken")
    fails, _ = check_draft.check(text, None)
    assert len(fails) == 2


def test_citation_without_entry_fails_and_unused_entry_warns() -> None:
    """A citation with no Sources entry fails; an uncited entry only warns."""
    fails, _ = check_draft.check(GOOD.replace("[1].", "[2]."), None)
    assert fails == ["[2] is cited but has no entry in the Sources appendix"]
    _, warns = check_draft.check(GOOD.replace("[1].", "."), None)
    assert warns == ["Sources entry [1] is never cited"]


def test_unknown_widget_fails() -> None:
    """A dashboard link to a widget id the manifest lacks fails."""
    fails, _ = check_draft.check(GOOD.replace("repo-growth", "made-up"), MANIFEST)
    assert len(fails) == 1 and "made-up" in fails[0]


def test_unknown_org_fails() -> None:
    """A dashboard link to an org the manifest lacks fails."""
    fails, _ = check_draft.check(GOOD.replace("org=hiero-ledger", "org=nope"), MANIFEST)
    assert len(fails) == 1 and "nope" in fails[0]


def test_empty_section_and_slots_warn() -> None:
    """An empty section and leftover maintainer slots both warn."""
    text = GOOD.replace("## Appendix: Sources", "## Goals\n\n## Appendix: Sources") + "\n> [MAINTAINER INPUT] goals\n"
    warns = check_draft.check(text, None)[1]
    assert "section 'Goals' is empty" in warns
    assert any("slot" in w for w in warns)


def test_number_dense_paragraph_warns_but_citations_and_years_do_not_count() -> None:
    """Dense paragraphs warn, and citations, code, link targets and years are not counted."""
    assert check_draft.count_numbers("In 2026 there were 5 [1] and 6 `7` (see [x](http://a/1/2/3)).") == 2
    dense = GOOD.replace("Hiero lists", "1 2 3 4 5 6 7 8 Hiero lists")
    assert any("numbers in one paragraph" in w for w in check_draft.check(dense, None)[1])


def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI exits 0 when clean, 1 on a failure and 2 on unreadable input."""
    draft = tmp_path / "d.md"
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(MANIFEST), encoding="utf-8")
    draft.write_text(GOOD, encoding="utf-8")
    assert check_draft.main([str(draft), "--manifest", str(manifest)]) == 0
    draft.write_text(GOOD.replace("[1].", "[3]."), encoding="utf-8")
    assert check_draft.main([str(draft)]) == 1
    assert "FAIL" in capsys.readouterr().out
    assert check_draft.main([str(tmp_path / "missing.md")]) == 2
