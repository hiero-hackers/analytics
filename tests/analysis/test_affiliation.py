"""Tests for the maintainer organisation-diversity analysis."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from hiero_analytics.analysis.affiliation import (
    INDEPENDENT,
    OTHER_LABEL,
    UNKNOWN_LABEL,
    build_affiliation_distribution,
    build_org_activity_heatmap,
    build_repo_affiliation_diversity,
    build_repo_org_composition,
    build_single_employer_repo_counts,
    build_single_employer_team_counts,
    build_team_affiliation_diversity,
    build_team_org_composition,
    classify_maintainers,
    filter_active_logins,
    load_affiliations,
    load_manual_logins,
    org_heatmap_chart_data,
    summarize_affiliation,
    top_n_with_other,
)

_ROLE_LOOKUP = {
    "org/solo-repo": {"alice": "maintainer", "bob": "maintainer"},  # both Hashgraph
    "org/mixed-repo": {"alice": "maintainer", "carol": "maintainer", "dave": "maintainer"},
    "org/no-maint": {"erin": "committer"},  # no maintainer -> excluded
}
_REPO_AFFILIATIONS = {"alice": "Hashgraph", "bob": "Hashgraph", "carol": "LimeChain", "dave": INDEPENDENT}


def _affiliations() -> dict[str, str]:
    return {
        "alice": "Hashgraph",
        "bob": "Hashgraph",
        "carol": "LimeChain",
        "dave": INDEPENDENT,
        "erin": INDEPENDENT,
        "frank": "?",  # explicit unknown -> dropped by loader
    }


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


def test_classify_maintainers_assigns_status():
    """Each maintainer is labelled affiliated, independent, or unknown."""
    maintainers = {"Alice", "carol", "dave", "zoe"}  # zoe absent -> unknown
    affiliations = {k: v for k, v in _affiliations().items() if v != "?"}

    df = classify_maintainers(maintainers, affiliations)

    by_login = df.set_index("login")
    assert by_login.loc["Alice", "status"] == "affiliated"
    assert by_login.loc["Alice", "organisation"] == "Hashgraph"
    assert by_login.loc["dave", "status"] == "independent"
    assert by_login.loc["zoe", "status"] == "unknown"
    assert pd.isna(by_login.loc["zoe", "organisation"])


def test_classify_maintainers_matches_login_case_insensitively():
    """Mixed-case logins still match a lowercased affiliations key."""
    df = classify_maintainers({"ALICE"}, {"alice": "Hashgraph"})
    assert df.iloc[0]["status"] == "affiliated"
    assert df.iloc[0]["organisation"] == "Hashgraph"


def test_build_distribution_folds_independents_and_sorts():
    """The distribution pools independents and excludes unknowns, sorted by count."""
    classified = classify_maintainers(
        {"alice", "bob", "carol", "dave", "erin", "zoe"},
        {k: v for k, v in _affiliations().items() if v != "?"},
    )

    dist = build_affiliation_distribution(classified)

    # Named employers + a single Independent row; unknown (zoe) excluded.
    assert list(dist["organisation"]) == ["Hashgraph", INDEPENDENT, "LimeChain"]
    assert dist[dist["organisation"] == "Hashgraph"]["maintainers"].iloc[0] == 2
    assert dist[dist["organisation"] == INDEPENDENT]["maintainers"].iloc[0] == 2
    assert "?" not in set(dist["organisation"])


def test_build_distribution_empty_frame():
    """An empty classification yields an empty distribution."""
    empty = pd.DataFrame(columns=["login", "organisation", "status"])
    assert build_affiliation_distribution(empty).empty


def test_summarize_counts_and_concentration():
    """Coverage counts and top-org share are computed over the known set."""
    classified = classify_maintainers(
        {"alice", "bob", "carol", "dave", "erin", "zoe"},
        {k: v for k, v in _affiliations().items() if v != "?"},
    )

    summary = summarize_affiliation(classified)

    assert summary["maintainers"] == 6
    assert summary["affiliated"] == 3  # alice, bob, carol
    assert summary["independent"] == 2  # dave, erin
    assert summary["unknown"] == 1  # zoe
    assert summary["distinct_orgs"] == 2  # Hashgraph, LimeChain
    assert summary["top_org"] == "Hashgraph"
    assert summary["top_share_pct"] == 40  # 2 of 5 known


def test_summarize_independents_lower_hhi():
    """Each independent is its own entity, so the independent tail reduces the HHI."""
    everyone_one_org = classify_maintainers(
        {"a", "b", "c", "d"}, {"a": "Hashgraph", "b": "Hashgraph", "c": "Hashgraph", "d": "Hashgraph"}
    )
    mixed = classify_maintainers(
        {"a", "b", "c", "d"},
        {"a": "Hashgraph", "b": "Hashgraph", "c": INDEPENDENT, "d": INDEPENDENT},
    )

    assert summarize_affiliation(everyone_one_org)["hhi"] == 10000  # monopoly
    assert summarize_affiliation(mixed)["hhi"] < 10000


def test_summarize_empty_is_zeroed():
    """Summarising an empty frame returns zeroed metrics, not an error."""
    empty = pd.DataFrame(columns=["login", "organisation", "status"])
    summary = summarize_affiliation(empty)
    assert summary["maintainers"] == 0
    assert summary["hhi"] == 0
    assert summary["top_org"] is None


def test_repo_diversity_flags_single_vendor_and_excludes_roleless():
    """Per-repo rows count maintainer employers; repos with no maintainer drop out."""
    df = build_repo_affiliation_diversity(_ROLE_LOOKUP, _REPO_AFFILIATIONS)

    by_repo = df.set_index("repo")
    assert "no-maint" not in by_repo.index  # only committers -> excluded
    # solo-repo: both maintainers at one employer -> single-vendor, sorted first.
    assert df.iloc[0]["repo"] == "solo-repo"
    assert by_repo.loc["solo-repo", "distinct_orgs"] == 1
    assert by_repo.loc["solo-repo", "top_org"] == "Hashgraph"
    assert by_repo.loc["solo-repo", "top_org_pct"] == 100
    # mixed-repo: Hashgraph + LimeChain + one independent.
    assert by_repo.loc["mixed-repo", "distinct_orgs"] == 2
    assert by_repo.loc["mixed-repo", "independent"] == 1


def test_repo_diversity_empty_role_lookup():
    """No maintainers anywhere yields an empty, correctly-typed frame."""
    assert build_repo_affiliation_diversity({}, {}).empty


def test_repo_org_composition_segments_and_counts():
    """Composition splits each repo's maintainers across employer / independent / unknown columns."""
    role_lookup = {
        "org/r": {"alice": "maintainer", "carol": "maintainer", "dave": "maintainer", "zoe": "maintainer"},
    }
    frame, segments = build_repo_org_composition(role_lookup, _REPO_AFFILIATIONS, top_n=6)

    assert INDEPENDENT in segments and UNKNOWN_LABEL in segments
    assert segments[-1] == UNKNOWN_LABEL  # unknown stacks last
    row = frame.set_index("repo").loc["r"]
    assert row["Hashgraph"] == 1
    assert row["LimeChain"] == 1
    assert row[INDEPENDENT] == 1
    assert row[UNKNOWN_LABEL] == 1  # zoe is unmapped


def test_repo_org_composition_sorts_most_concentrated_first():
    """Repos where one employer dominates are ordered ahead of cross-org ones."""
    role_lookup = {
        "org/pure": {"a": "maintainer", "b": "maintainer"},   # 100% Hashgraph
        "org/mixed": {"a": "maintainer", "c": "maintainer"},  # 50% Hashgraph / 50% LimeChain
    }
    affiliations = {"a": "Hashgraph", "b": "Hashgraph", "c": "LimeChain"}
    frame, _ = build_repo_org_composition(role_lookup, affiliations)
    assert list(frame["repo"]) == ["pure", "mixed"]


def test_repo_org_composition_groups_equal_concentration_by_colour():
    """Bars at the same concentration are grouped by their leading org (colour order)."""
    role_lookup = {
        "org/lime1": {"c": "maintainer", "d": "maintainer"},  # 100% LimeChain
        "org/hash1": {"a": "maintainer", "b": "maintainer"},  # 100% Hashgraph
        "org/lime2": {"c": "maintainer", "d2": "maintainer"},  # 100% LimeChain
        "org/hash2": {"a": "maintainer", "b2": "maintainer"},  # 100% Hashgraph
        "org/hash3": {"a": "maintainer", "e": "maintainer"},   # 100% Hashgraph
    }
    affiliations = {
        "a": "Hashgraph", "b": "Hashgraph", "b2": "Hashgraph", "e": "Hashgraph",
        "c": "LimeChain", "d": "LimeChain", "d2": "LimeChain",
    }
    # Hashgraph has more total seats, so it is the first (leftmost) colour; all its
    # bars must come before LimeChain's, even though every bar is equally concentrated.
    frame, _ = build_repo_org_composition(role_lookup, affiliations)
    assert list(frame["repo"]) == ["hash1", "hash2", "hash3", "lime1", "lime2"]


def test_repo_org_composition_pools_into_other():
    """Beyond top_n employers, the long tail pools into a single 'Other orgs' column."""
    role_lookup = {"org/r": {f"u{i}": "maintainer" for i in range(4)}}
    affiliations = {"u0": "A", "u1": "B", "u2": "C", "u3": "D"}

    frame, segments = build_repo_org_composition(role_lookup, affiliations, top_n=2)

    assert OTHER_LABEL in segments
    assert frame.set_index("repo").loc["r", OTHER_LABEL] == 2  # C and D pooled


def test_repo_org_composition_empty():
    """An empty role lookup yields an empty frame and no segments."""
    frame, segments = build_repo_org_composition({}, {})
    assert frame.empty
    assert segments == []


_TEAMS = {
    "admins": {"alice", "bob"},          # both Hashgraph -> single-employer
    "steering": {"alice", "carol"},      # Hashgraph + LimeChain -> diverse
    "solo": {"alice"},                   # below min_members -> skipped
    "mixed-tail": {"alice", "dave", "zoe"},  # Hashgraph + independent + unknown
}
_TEAM_AFFILIATIONS = {"alice": "Hashgraph", "bob": "Hashgraph", "carol": "LimeChain", "dave": INDEPENDENT}


def test_team_diversity_flags_single_employer_and_skips_small():
    """A team whose resolved members share one employer is flagged; sub-min teams drop."""
    df = build_team_affiliation_diversity(_TEAMS, _TEAM_AFFILIATIONS, min_members=2)

    by_team = df.set_index("team")
    assert "solo" not in by_team.index
    assert bool(by_team.loc["admins", "single_employer"]) is True
    assert by_team.loc["admins", "hhi"] == 10000
    assert bool(by_team.loc["steering", "single_employer"]) is False
    # An independent member means the team is not one-employer-controlled.
    assert bool(by_team.loc["mixed-tail", "single_employer"]) is False
    assert by_team.loc["mixed-tail", "unknown"] == 1


def test_team_diversity_sorted_by_concentration():
    """Most concentrated teams come first."""
    df = build_team_affiliation_diversity(_TEAMS, _TEAM_AFFILIATIONS, min_members=2)
    assert df.iloc[0]["hhi"] >= df.iloc[-1]["hhi"]


def test_team_diversity_empty():
    """No teams above the size floor yields an empty frame."""
    assert build_team_affiliation_diversity({"solo": {"alice"}}, _TEAM_AFFILIATIONS).empty


def test_single_employer_team_counts_groups_by_controlling_org():
    """Single-employer teams roll up by the org that controls them."""
    df = build_team_affiliation_diversity(
        {"a": {"alice", "bob"}, "b": {"alice", "bob"}, "c": {"carol", "carol2"}},
        {"alice": "Hashgraph", "bob": "Hashgraph", "carol": "LimeChain", "carol2": "LimeChain"},
        min_members=2,
    )
    counts = build_single_employer_team_counts(df).set_index("organisation")["teams"]
    assert counts["Hashgraph"] == 2
    assert counts["LimeChain"] == 1


def test_single_employer_team_counts_empty():
    """No captured teams yields an empty frame."""
    import pandas as pd

    empty = pd.DataFrame(columns=["team", "single_employer", "top_org"])
    assert build_single_employer_team_counts(empty).empty


def test_single_employer_repo_counts_groups_by_controlling_org():
    """Single-employer repos roll up by the org whose maintainers solely hold them."""
    role_lookup = {
        "org/solo-a": {"alice": "maintainer", "bob": "maintainer"},      # all Hashgraph
        "org/solo-b": {"alice": "maintainer", "carol": "maintainer"},    # all Hashgraph
        "org/lime": {"dave": "maintainer", "erin": "maintainer"},        # all LimeChain
        "org/mixed": {"alice": "maintainer", "dave": "maintainer"},      # cross-org -> excluded
        "org/with-indie": {"alice": "maintainer", "frank": "maintainer"},  # has independent -> excluded
    }
    affiliations = {
        "alice": "Hashgraph", "bob": "Hashgraph", "carol": "Hashgraph",
        "dave": "LimeChain", "erin": "LimeChain", "frank": INDEPENDENT,
    }
    diversity = build_repo_affiliation_diversity(role_lookup, affiliations)
    counts = build_single_employer_repo_counts(diversity).set_index("organisation")["repos"]
    assert counts["Hashgraph"] == 2
    assert counts["LimeChain"] == 1
    assert "mixed" not in " ".join(counts.index)  # cross-org repo not counted


def test_single_employer_repo_counts_empty():
    """No captured repos yields an empty frame."""
    assert build_single_employer_repo_counts(pd.DataFrame()).empty


def test_team_diversity_lists_organisation_mix():
    """The diversity table carries each team's full employer breakdown."""
    df = build_team_affiliation_diversity(_TEAMS, _TEAM_AFFILIATIONS, min_members=2)
    mix = df.set_index("team").loc["mixed-tail", "organisations"]
    assert "Hashgraph 1" in mix
    assert "Independent 1" in mix


def test_team_org_composition_filters_and_segments():
    """Composition covers teams meeting the resolved-member floor, split by employer."""
    role = {f"u{i}": "Hashgraph" for i in range(3)}
    role.update({"v0": "LimeChain", "v1": INDEPENDENT})
    teams = {
        "big": {"u0", "u1", "u2", "v0"},   # 4 resolved -> included
        "small": {"u0", "v1"},              # 2 resolved -> excluded at min_resolved=4
    }
    frame, segments = build_team_org_composition(teams, role, min_resolved=4)

    assert list(frame["team"]) == ["big"]  # only the team above the floor
    assert "Hashgraph" in segments
    assert frame.set_index("team").loc["big", "Hashgraph"] == 3


def test_team_org_composition_empty_when_below_floor():
    """No team meets the floor -> empty frame and no segments."""
    frame, segments = build_team_org_composition({"t": {"a", "b"}}, {"a": "Hashgraph"}, min_resolved=4)
    assert frame.empty
    assert segments == []


def _contributor_heatmap() -> pd.DataFrame:
    return pd.DataFrame([
        {"contributor name": "Alice", "role": "Maintainer", "activity score": 10, "2026-01": 6, "2026-02": 4},
        {"contributor name": "bob", "role": "Committer", "activity score": 5, "2026-01": 5, "2026-02": 0},
        {"contributor name": "carol", "role": "Maintainer", "activity score": 8, "2026-01": 3, "2026-02": 5},
        {"contributor name": "zoe", "role": "General User", "activity score": 99, "2026-01": 99, "2026-02": 0},
    ])


def test_org_activity_heatmap_aggregates_and_excludes_unmapped():
    """Per-contributor scores sum by employer; unmapped contributors drop out."""
    aff = {"alice": "Hashgraph", "bob": "Hashgraph", "carol": "LimeChain"}
    org_hm = build_org_activity_heatmap(_contributor_heatmap(), aff)

    by = org_hm.set_index("organisation")
    assert by.loc["Hashgraph", "activity score"] == 15  # alice + bob
    assert by.loc["Hashgraph", "2026-01"] == 11
    assert org_hm.iloc[0]["organisation"] == "Hashgraph"  # busiest first
    assert UNKNOWN_LABEL not in set(org_hm["organisation"])  # zoe excluded


def test_org_activity_heatmap_can_include_unknown():
    """With include_unknown, unmapped contributors roll up into an Unknown row."""
    org_hm = build_org_activity_heatmap(_contributor_heatmap(), {}, include_unknown=True)
    assert org_hm.iloc[0]["organisation"] == UNKNOWN_LABEL


def test_org_heatmap_chart_data_shape_and_empty():
    """Chart data returns aligned values/labels, and None on an empty frame."""
    aff = {"alice": "Hashgraph", "bob": "Hashgraph", "carol": "LimeChain"}
    values, rows, cols = org_heatmap_chart_data(build_org_activity_heatmap(_contributor_heatmap(), aff))
    assert rows == ["Hashgraph", "LimeChain"]
    assert cols == ["2026-01", "2026-02"]
    assert values.shape == (2, 2)
    assert org_heatmap_chart_data(pd.DataFrame(columns=["organisation", "activity score"])) is None


def test_filter_active_logins_keeps_recently_active():
    """Only logins with activity at or after the cutoff are kept; case-insensitive."""
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    last_active = {
        "alice": (datetime(2026, 3, 1, tzinfo=UTC), "Alice"),   # after cutoff -> active
        "bob": (datetime(2025, 6, 1, tzinfo=UTC), "Bob"),       # before cutoff -> quiet
        "carol": (datetime(2026, 1, 1, tzinfo=UTC), "Carol"),   # exactly cutoff -> active
    }
    active = filter_active_logins({"Alice", "bob", "carol", "dave"}, last_active, cutoff)

    assert active == {"Alice", "carol"}  # dave absent (no activity), bob too old


def test_top_n_with_other_folds_the_tail():
    """Beyond top_n, the remaining rows collapse into a single 'Other (k)' row."""
    dist = pd.DataFrame(
        {"organisation": ["A", "B", "C", "D", "E"], "maintainers": [10, 8, 6, 4, 2]}
    )
    folded = top_n_with_other(dist, "organisation", "maintainers", top_n=3)
    assert list(folded["organisation"]) == ["A", "B", "C", "Other (2)"]
    assert folded[folded["organisation"] == "Other (2)"]["maintainers"].iloc[0] == 6  # 4 + 2


def test_top_n_with_other_noop_when_small():
    """A distribution already within top_n is returned sorted, unfolded."""
    dist = pd.DataFrame({"organisation": ["A", "B"], "maintainers": [2, 9]})
    folded = top_n_with_other(dist, "organisation", "maintainers", top_n=6)
    assert list(folded["organisation"]) == ["B", "A"]  # sorted desc, no Other row
    assert "Other" not in " ".join(folded["organisation"])
