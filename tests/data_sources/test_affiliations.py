"""Tests for reading the curated affiliations map."""

from __future__ import annotations

from hiero_analytics.data_sources.affiliations import load_affiliations, load_manual_logins


def test_load_affiliations_lowercases_and_drops_unknown(tmp_path):
    """Logins lowercase and explicit-unknown markers drop out of the loaded map."""
    path = tmp_path / "affiliations.yaml"
    path.write_text(
        'Alice: "Hashgraph"\nBob: "Independent"\nCarol: "?"\nDave: "unknown"\n',
        encoding="utf-8",
    )

    mapping = load_affiliations(path)

    assert mapping == {"alice": "Hashgraph", "bob": "Independent"}


def test_load_affiliations_missing_file_returns_empty(tmp_path):
    """A missing affiliations file yields an empty map, not an error."""
    assert load_affiliations(tmp_path / "nope.yaml") == {}


def test_load_manual_logins_detects_marked_rows(tmp_path):
    """Only rows whose comment is marked manual/MANUAL are flagged as hand-corrected."""
    path = tmp_path / "affiliations.yaml"
    path.write_text(
        'alice: "Hashgraph"  # maintainer · Alice\n'
        'bob: "LimeChain"  # manual: confirmed by hand\n'
        'carol: "Hedera"  # maintainer · MANUAL — moved (resolver: Hashgraph)\n'
        'dave: "?"  # committer · Dave\n',
        encoding="utf-8",
    )
    assert load_manual_logins(path) == {"bob", "carol"}
    assert load_manual_logins(tmp_path / "nope.yaml") == set()


def test_load_affiliations_resolves_misiek_blocky_and_seanbohan(tmp_path):
    """The two contributors from issue #389 resolve to their correct orgs."""
    path = tmp_path / "affiliations.yaml"
    path.write_text(
        'misiek-blocky: "BlockyDevs"  # manual\nseanbohan: "Linux Foundation"  # manual\n',
        encoding="utf-8",
    )

    mapping = load_affiliations(path)

    assert mapping == {"misiek-blocky": "BlockyDevs", "seanbohan": "Linux Foundation"}
    assert load_manual_logins(path) == {"misiek-blocky", "seanbohan"}
