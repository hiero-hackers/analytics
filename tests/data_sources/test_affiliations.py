"""Tests for reading the affiliation map: a generated file plus a hand-kept overrides file.

``load_affiliations(path)`` looks for ``affiliation_overrides.yaml`` beside ``path``, so
fixtures in ``tmp_path`` never see the committed overrides. The merge tests still pass
``overrides_path`` explicitly; one test pins the sibling default.
"""

from __future__ import annotations

import logging

from hiero_analytics.data_sources.affiliations import (
    load_affiliations,
    load_manual_logins,
    load_override_rows,
    load_overrides,
)


def _write(tmp_path, name: str, text: str):
    """Write ``text`` to ``tmp_path / name`` and return the path."""
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# -- load_affiliations: generated file alone ------------------------------------


def test_load_affiliations_lowercases_and_drops_unknown(tmp_path):
    """Logins lowercase and explicit-unknown markers drop out of the loaded map."""
    generated = _write(
        tmp_path,
        "affiliations.yaml",
        'Alice: "Hashgraph"\nBob: "Independent"\nCarol: "?"\nDave: "unknown"\n',
    )

    mapping = load_affiliations(generated)

    assert mapping == {"alice": "Hashgraph", "bob": "Independent"}


def test_load_affiliations_missing_overrides_file_yields_the_generated_map(tmp_path):
    """Without an overrides file the merged map is exactly the generated one."""
    generated = _write(tmp_path, "affiliations.yaml", 'alice: "Hashgraph"\nbob: "LimeChain"\n')

    assert load_affiliations(generated, tmp_path / "no_overrides.yaml") == {"alice": "Hashgraph", "bob": "LimeChain"}


def test_load_affiliations_both_files_missing_returns_empty(tmp_path):
    """A missing generated file with no sibling overrides yields an empty map, not an error."""
    assert load_affiliations(tmp_path / "nope.yaml") == {}
    assert load_affiliations(tmp_path / "nope.yaml", tmp_path / "nope_either.yaml") == {}


def test_load_affiliations_empty_files_return_empty(tmp_path):
    """A zero-byte or comment-only file (yaml parses to None) is an empty map, not a crash."""
    generated = _write(tmp_path, "affiliations.yaml", "")
    overrides = _write(tmp_path, "affiliation_overrides.yaml", "# nothing corrected yet\n")

    assert load_affiliations(generated, overrides) == {}


# -- load_affiliations: merging ---------------------------------------------------


def test_load_affiliations_defaults_overrides_to_the_sibling_file(tmp_path):
    """With only ``path`` given, the overrides file beside it is merged, not the committed one."""
    generated = _write(tmp_path, "affiliations.yaml", 'alice: "Hashgraph"\nbob: "LimeChain"\ncarol: "Hedera"\n')
    _write(tmp_path, "affiliation_overrides.yaml", 'alice: "Acme"  # r\ncarol: "?"  # r\nerin: "Independent"  # r\n')

    assert load_affiliations(generated) == {"alice": "Acme", "bob": "LimeChain", "erin": "Independent"}


def test_load_affiliations_sibling_default_ignores_overrides_in_other_directories(tmp_path):
    """The default looks only beside ``path``: an overrides file elsewhere is never merged."""
    folder = tmp_path / "generated"
    folder.mkdir()
    generated = _write(folder, "affiliations.yaml", 'alice: "Hashgraph"\n')
    _write(tmp_path, "affiliation_overrides.yaml", 'alice: "Acme"  # r\n')  # parent folder, not beside it

    assert load_affiliations(generated) == {"alice": "Hashgraph"}


def test_load_affiliations_explicit_overrides_path_beats_the_sibling(tmp_path):
    """An explicit ``overrides_path`` is used instead of the sibling file."""
    generated = _write(tmp_path, "affiliations.yaml", 'alice: "Hashgraph"\n')
    _write(tmp_path, "affiliation_overrides.yaml", 'alice: "Sibling"  # r\n')
    chosen = _write(tmp_path, "elsewhere.yaml", 'alice: "Explicit"  # r\n')

    assert load_affiliations(generated, chosen) == {"alice": "Explicit"}


def test_load_affiliations_override_wins_over_generated_value(tmp_path):
    """Where both files name a login the override wins; untouched logins pass through."""
    generated = _write(
        tmp_path,
        "affiliations.yaml",
        'alice: "Hashgraph"  # maintainer · Alice\nbob: "LimeChain"  # committer · Bob\ncarol: "Hedera"\n',
    )
    overrides = _write(
        tmp_path,
        "affiliation_overrides.yaml",
        'alice: "Acme"  # confirmed on a call\nCAROL: "Independent"  # freelance since 2025\n',
    )

    mapping = load_affiliations(generated, overrides)

    assert mapping == {"alice": "Acme", "bob": "LimeChain", "carol": "Independent"}


def test_load_affiliations_override_adds_a_login_the_generated_file_lacks(tmp_path):
    """An override for a login on no roster still applies: it outlives the person's spell on the roster."""
    generated = _write(tmp_path, "affiliations.yaml", 'alice: "Hashgraph"\n')
    overrides = _write(tmp_path, "affiliation_overrides.yaml", 'erin: "Linux Foundation"  # left the roster\n')

    assert load_affiliations(generated, overrides) == {"alice": "Hashgraph", "erin": "Linux Foundation"}


def test_load_affiliations_override_question_mark_unsets_a_generated_value(tmp_path):
    """An override of '?' removes a login the resolver guessed wrong; it does not keep the guess."""
    generated = _write(tmp_path, "affiliations.yaml", 'alice: "Hashgraph"\nbob: "LimeChain"\n')
    overrides = _write(
        tmp_path, "affiliation_overrides.yaml", 'alice: "?"  # resolver guess is wrong, true answer unknown\n'
    )

    mapping = load_affiliations(generated, overrides)

    assert mapping == {"bob": "LimeChain"}
    assert "alice" not in mapping


def test_load_affiliations_override_replaces_a_generated_unknown(tmp_path):
    """A hand correction can place a login the resolver left as '?'."""
    generated = _write(tmp_path, "affiliations.yaml", 'dave: "?"  # team\n')
    overrides = _write(tmp_path, "affiliation_overrides.yaml", 'dave: "Acme"  # says so on profile\n')

    assert load_affiliations(generated, overrides) == {"dave": "Acme"}


def test_load_affiliations_missing_generated_file_yields_just_the_overrides(tmp_path, caplog):
    """With no generated file the overrides still load, and the absence is logged as a warning."""
    overrides = _write(
        tmp_path,
        "affiliation_overrides.yaml",
        'alice: "Acme"  # reason\nbob: "?"  # unset\n',
    )

    with caplog.at_level(logging.WARNING):
        mapping = load_affiliations(tmp_path / "affiliations.yaml", overrides)

    assert mapping == {"alice": "Acme"}
    assert any("not found" in record.getMessage() for record in caplog.records)


# -- load_overrides / load_manual_logins / load_override_rows --------------------------


def test_load_overrides_keeps_unknown_markers_and_lowercases(tmp_path):
    """The raw override map keeps '?' (it is a meaningful instruction) and lowercases logins."""
    overrides = _write(tmp_path, "affiliation_overrides.yaml", 'Alice: "Acme"  # r\nBOB: "?"  # r\n')

    assert load_overrides(overrides) == {"alice": "Acme", "bob": "?"}
    assert load_overrides(tmp_path / "nope.yaml") == {}


def test_load_manual_logins_reads_the_overrides_file(tmp_path):
    """Every row of the overrides file is a hand-corrected login, lowercased; a missing file has none."""
    overrides = _write(
        tmp_path,
        "affiliation_overrides.yaml",
        '# header comment\n\nBob: "Acme"  # confirmed by hand\nCAROL: "?"  # unset\ndave: "Independent"  # freelance\n',
    )

    assert load_manual_logins(overrides) == {"bob", "carol", "dave"}
    assert load_manual_logins(tmp_path / "nope.yaml") == set()


def test_load_manual_logins_ignores_markers_in_the_generated_file(tmp_path):
    """A '# manual' comment in the generated file no longer marks anything; only the overrides file does."""
    generated = _write(tmp_path, "affiliations.yaml", 'bob: "LimeChain"  # manual: confirmed by hand\n')

    assert load_manual_logins(tmp_path / "affiliation_overrides.yaml") == set()
    assert load_affiliations(generated, tmp_path / "affiliation_overrides.yaml") == {"bob": "LimeChain"}


def test_load_override_rows_returns_value_and_reason(tmp_path):
    """Each row yields (value, reason) with the reason being the trailing comment, empty when absent."""
    overrides = _write(
        tmp_path,
        "affiliation_overrides.yaml",
        "# header comment: not a row\n"
        "\n"
        'Alice: "Acme"  # confirmed via call\n'
        'bob: "Independent"\n'
        'carol: "?"  # Carol · left the company, new employer unknown\n'
        'dave: "Foo Bar"   #   padded reason   \n',
    )

    assert load_override_rows(overrides) == {
        "alice": ("Acme", "confirmed via call"),
        "bob": ("Independent", ""),
        "carol": ("?", "Carol · left the company, new employer unknown"),
        "dave": ("Foo Bar", "padded reason"),
    }


def test_load_override_rows_missing_file_returns_empty(tmp_path):
    """A missing overrides file has no rows."""
    assert load_override_rows(tmp_path / "nope.yaml") == {}


def test_load_override_rows_agrees_with_load_overrides_on_logins_and_values(tmp_path):
    """The reason-aware reader and the yaml reader see the same logins and values."""
    overrides = _write(
        tmp_path,
        "affiliation_overrides.yaml",
        'Alice: "Acme"  # r1\nbob: "?"  # r2\ncarol: "Linux Foundation"  # r3\n',
    )

    rows = load_override_rows(overrides)

    assert {login: value for login, (value, _reason) in rows.items()} == load_overrides(overrides)


# -- regression: issue #389 -----------------------------------------------------------


def test_load_affiliations_resolves_misiek_blocky_and_seanbohan(tmp_path):
    """The two contributors from issue #389 resolve to their correct orgs through the overrides file."""
    generated = _write(
        tmp_path,
        "affiliations.yaml",
        'alice: "Hashgraph"  # maintainer · Alice\nmisiek-blocky: "?"  # committer\nseanbohan: "?"  # maintainer\n',
    )
    overrides = _write(
        tmp_path,
        "affiliation_overrides.yaml",
        'misiek-blocky: "BlockyDevs"  # issue #389\nseanbohan: "Linux Foundation"  # issue #389\n',
    )

    # Without the overrides the resolver leaves both unplaced...
    assert load_affiliations(generated, tmp_path / "no_overrides.yaml") == {"alice": "Hashgraph"}

    # ...and with them both resolve, and both are reported as hand-corrected.
    assert load_affiliations(generated, overrides) == {
        "alice": "Hashgraph",
        "misiek-blocky": "BlockyDevs",
        "seanbohan": "Linux Foundation",
    }
    assert load_manual_logins(overrides) == {"misiek-blocky", "seanbohan"}


def test_load_override_rows_keeps_a_hash_inside_a_quoted_value(tmp_path):
    """The reason starts at the first '#' outside the quotes, so a value like "C# Corp" survives intact."""
    path = tmp_path / "affiliation_overrides.yaml"
    path.write_text('alice: "C# Corp"  # badge at the summit\n', encoding="utf-8")

    assert load_override_rows(path) == {"alice": ("C# Corp", "badge at the summit")}
    assert load_overrides(path) == {"alice": "C# Corp"}
