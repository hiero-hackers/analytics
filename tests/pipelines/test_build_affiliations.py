"""Tests for the affiliation resolver's signal-precedence logic.

The ordering (GPG > profile email > MAINTAINERS.md > company field > bio >
org membership > small/solo domain > commit email) is exactly the kind of
subtle ranking that regresses silently — these tests pin it.
"""

from __future__ import annotations

import csv

import pytest
import requests

import hiero_analytics.pipelines.build_affiliations as ba
from hiero_analytics.pipelines.build_affiliations import (
    _get_json,
    _write_audit,
    _write_yaml,
    commit_author_org,
    external_company,
    fetch_linkedin,
    fetch_maintainers_affiliations,
    load_manual_overrides,
    org_from_bio,
    org_from_email,
    parse_maintainers_md,
    resolve_participant,
)


def _profile(**overrides) -> dict:
    profile = {"login": "alice", "name": "Alice", "company": "", "email": "", "bio": "", "orgs": []}
    profile.update(overrides)
    return profile


def _resolve(profile=None, gpg_emails=(), md_org=None, commit_org=None):
    calls = {"commit": 0}

    def fetch_commit_org():
        calls["commit"] += 1
        return commit_org

    result = resolve_participant(profile or _profile(), list(gpg_emails), md_org, fetch_commit_org)
    result["_commit_calls"] = calls["commit"]
    return result


# -- precedence ordering ------------------------------------------------------


def test_gpg_outranks_every_other_signal():
    """A GPG UID email wins over profile email, MAINTAINERS.md, and company."""
    result = _resolve(
        profile=_profile(email="alice@hedera.com", company="LimeChain"),
        gpg_emails=["alice@hashgraph.com"],
        md_org="OpenElements",
    )
    assert result["resolved"] == "Hashgraph"
    assert result["decided_by"] == "gpg-key email"


def test_profile_email_outranks_maintainers_md_and_company():
    """With no GPG signal, the profile email decides."""
    result = _resolve(profile=_profile(email="alice@limechain.tech", company="OpenElements"), md_org="Hedera")
    assert result["resolved"] == "LimeChain"
    assert result["decided_by"] == "profile email"


def test_maintainers_md_outranks_company_field():
    """The self-declared MAINTAINERS.md company beats the profile company field."""
    result = _resolve(profile=_profile(company="OpenElements"), md_org="Hedera")
    assert result["resolved"] == "Hedera"
    assert result["decided_by"] == "MAINTAINERS.md"


def test_company_outranks_bio_and_membership():
    """The company field beats a bio mention and org membership."""
    result = _resolve(profile=_profile(company="LimeChain", bio="devrel @hashgraph", orgs=["openelements"]))
    assert result["resolved"] == "LimeChain"
    assert result["decided_by"] == "company field"


def test_membership_is_the_weakest_ecosystem_signal():
    """Org membership resolves only when nothing stronger is present."""
    result = _resolve(profile=_profile(orgs=["limechain"]))
    assert result["resolved"] == "LimeChain"
    assert result["decided_by"] == "org membership"


def test_commit_email_is_lazy_last_resort():
    """The commit-email backup is only consulted when nothing else resolves."""
    unresolved = _resolve(commit_org="Hashgraph")
    assert unresolved["resolved"] == "Hashgraph"
    assert unresolved["decided_by"] == "commit email"
    assert unresolved["_commit_calls"] == 1

    resolved_earlier = _resolve(profile=_profile(email="alice@hashgraph.com"), commit_org="Hedera")
    assert resolved_earlier["resolved"] == "Hashgraph"
    assert resolved_earlier["_commit_calls"] == 0  # never spent the API calls


def test_external_company_outranks_stale_ecosystem_membership():
    """A named external employer beats a lapsed ecosystem org membership."""
    result = _resolve(profile=_profile(company="Robinhood", orgs=["hashgraph"]))
    assert result["resolved"] == "Robinhood"
    assert result["decided_by"] == "company field"


# -- identity edge cases ------------------------------------------------------


def test_noreply_addresses_are_not_identity():
    """Obfuscated noreply emails resolve nothing and grant no identity."""
    result = _resolve(gpg_emails=["12345+alice@users.noreply.github.com"])
    assert result["resolved"] is None
    assert result["status"] == "unknown"
    assert result["decided_by"] == "obfuscated email only"


def test_personal_email_means_independent():
    """A real personal email is identity without affiliation -> independent."""
    result = _resolve(profile=_profile(email="alice@gmail.com"))
    assert result["status"] == "independent"
    assert result["decided_by"] == "personal email only"
    assert org_from_email("alice@gmail.com") is None


def test_multi_mention_bio_reads_as_interests():
    """Several @-mentions in a bio are interests, not an employer."""
    assert org_from_bio("fan of @hashgraph and @limechain") is None
    assert org_from_bio("devrel @hashgraph") == "Hashgraph"


def test_agreeing_signals_upgrade_confidence():
    """Two agreeing signals mark the resolution as verified."""
    result = _resolve(profile=_profile(email="alice@hashgraph.com", company="Hashgraph"))
    assert result["confidence"] == "verified"
    single = _resolve(profile=_profile(email="alice@hashgraph.com"))
    assert single["confidence"] == "single"


def test_external_company_rejects_junk_and_prose():
    """Junk placeholders and free-text never mint an employer."""
    assert external_company("Self-Employed") is None
    assert external_company("guy who builds things for fun and profit") is None
    assert external_company("hiero-ledger") is None
    assert external_company("Robinhood") == "Robinhood"


# -- supporting parsers -------------------------------------------------------


def test_parse_maintainers_md_reads_pipe_tables():
    """GitHub handles and company cells come out of any table with a GitHub column."""
    md = (
        "| Name | GitHub ID | Company Affiliation |\n"
        "| --- | --- | --- |\n"
        "| Alice | [@alice](https://github.com/alice) | LimeChain |\n"
        "| Bob | bob | - |\n"
    )
    assert list(parse_maintainers_md(md)) == [("alice", "LimeChain"), ("bob", "-")]


def test_load_manual_overrides_survive_regeneration(tmp_path):
    """Rows flagged '# manual' are preserved with their reason."""
    yaml = tmp_path / "affiliations.yaml"
    yaml.write_text(
        'alice: "Hashgraph"  # maintainer · Alice\n'
        'bob: "Acme"  # manual: confirmed via call\n'
        'carol: "?"  # team · MANUAL — left the company (resolver: Hashgraph)\n',
        encoding="utf-8",
    )
    overrides = load_manual_overrides(yaml)
    assert "alice" not in overrides
    assert overrides["bob"] == ("Acme", "confirmed via call")
    assert overrides["carol"][0] == "?"


# -- I/O: writers round-trip and provenance -----------------------------------


def _full_row(login, *, profile=None, gpg_emails=(), md_org=None, commit_org=None, manual=None):
    """Assemble a YAML/audit row exactly as main() does: profile + resolution + manual."""
    prof = {"login": login, "name": login.title(), "company": "", "email": "", "bio": "", "orgs": []}
    prof.update(profile or {})
    row = dict(prof)
    row.update(resolve_participant(prof, list(gpg_emails), md_org, lambda: commit_org))
    row["linkedin"] = ""
    row["auto_resolved"] = row["resolved"]
    row["auto_status"] = row["status"]
    row["manual"] = bool(manual)
    row["manual_reason"] = ""
    if manual:
        value, reason = manual
        row["manual_reason"] = reason
        if value in ("", "?"):
            row["status"], row["resolved"] = "unknown", None
        elif value.lower() == "independent":
            row["status"], row["resolved"] = "independent", None
        else:
            row["status"], row["resolved"] = "affiliated", value
        row["decided_by"] = "manual override"
    return row


def test_write_yaml_round_trips_through_load_manual_overrides(tmp_path):
    """A manual override written by _write_yaml is read back intact by load_manual_overrides.

    This is the regeneration contract: hand-corrected rows must survive a rewrite.
    The read side is tested elsewhere; this pins that the *writer* emits the exact
    '# manual: reason' shape the reader recognises.
    """
    rows = [
        _full_row("alice", profile={"email": "alice@hashgraph.com"}),
        # bob resolves to Hashgraph automatically, but a human overrode it to Acme.
        _full_row("bob", profile={"email": "bob@hashgraph.com"}, manual=("Acme", "confirmed via call")),
        _full_row("carol", profile={"email": "carol@gmail.com"}),
    ]
    yaml_path = tmp_path / "affiliations.yaml"
    _write_yaml(rows, yaml_path, scope_of=lambda _login: "maintainer", maintainer_count=1)

    overrides = load_manual_overrides(yaml_path)
    assert overrides == {"bob": ("Acme", "confirmed via call")}

    text = yaml_path.read_text(encoding="utf-8")
    assert 'alice: "Hashgraph"' in text
    assert 'bob: "Acme"' in text
    assert "MANUAL — confirmed via call (resolver: Hashgraph)" in text  # competing guess recorded
    assert 'carol: "Independent"' in text


def test_write_audit_redacts_emails_and_neutralises_formula_injection(tmp_path):
    """The audit CSV logs only email domains and defuses spreadsheet formula injection."""
    row = _full_row(
        "mallory",
        profile={
            "name": "=cmd|' /c calc'!A1",  # classic CSV-injection payload in an attacker-set field
            "email": "mallory@hashgraph.com",
            "company": "Hashgraph",
        },
    )
    audit_path = tmp_path / "audit.csv"
    _write_audit([row], audit_path)

    rows = list(csv.reader(audit_path.read_text(encoding="utf-8").splitlines()))
    header, data = rows[0], rows[1]
    record = dict(zip(header, data, strict=True))

    # Domain only, never the full address; the leading '@' is itself a formula
    # prefix, so csv_safe also quotes it.
    assert record["profile_email"] == "'@hashgraph.com"
    assert record["name"].startswith("'=")  # formula prefix neutralised with a leading quote


# -- I/O: network helpers map failures to the tool's contracts ----------------


def test_get_json_maps_any_request_error_to_none():
    """_get_json returns None on any transport error (callers read None as 'absent')."""

    class _Boom:
        def get(self, _url, **_kwargs):
            raise requests.ConnectionError("down")

    assert _get_json(_Boom(), "https://api.github.com/whatever") is None


def test_fetch_maintainers_affiliations_resolves_single_declared_company(monkeypatch):
    """A handle declaring one resolvable company across MAINTAINERS.md files maps to that org."""
    import base64

    md = "| GitHub ID | Company Affiliation |\n| --- | --- |\n| alice | LimeChain |\n"
    encoded = base64.b64encode(md.encode()).decode()

    def fake_get_json(_client, url, params=None):
        if url.endswith("/repos"):
            # One page of repos, then an empty page to stop the loop.
            return [{"name": "repo1"}] if (params or {}).get("page") == 1 else []
        if url.endswith("/MAINTAINERS.md"):
            return {"content": encoded}
        return None

    monkeypatch.setattr(ba, "_get_json", fake_get_json)
    monkeypatch.setattr(ba, "PARTICIPANT_ORGS", ("hiero-ledger",))

    assert fetch_maintainers_affiliations(object()) == {"alice": "LimeChain"}


def test_commit_author_org_picks_the_dominant_employer_domain(monkeypatch):
    """The commit backup returns the most common resolvable employer email domain."""

    def fake_get_json(_client, _url, params=None):
        return {
            "items": [
                {"commit": {"author": {"email": "x@hashgraph.com"}}},
                {"commit": {"author": {"email": "y@hashgraph.com"}}},
                {"commit": {"author": {"email": "z@gmail.com"}}},  # personal -> unresolved
            ]
        }

    monkeypatch.setattr(ba, "_get_json", fake_get_json)
    monkeypatch.setattr(ba, "PARTICIPANT_ORGS", ("hiero-ledger",))

    assert commit_author_org(object(), "alice") == "Hashgraph"


def test_commit_author_org_returns_none_when_nothing_resolves(monkeypatch):
    """No resolvable commit emails -> no backup affiliation."""
    monkeypatch.setattr(ba, "_get_json", lambda *_a, **_k: None)
    monkeypatch.setattr(ba, "PARTICIPANT_ORGS", ("hiero-ledger",))
    assert commit_author_org(object(), "ghost") is None


def test_fetch_linkedin_returns_url_only_for_linkedin_accounts(monkeypatch):
    """fetch_linkedin surfaces a linked LinkedIn URL and ignores other providers."""
    monkeypatch.setattr(
        ba,
        "_get_json",
        lambda *_a, **_k: [
            {"provider": "twitter", "url": "https://twitter.com/alice"},
            {"provider": "linkedin", "url": "https://www.linkedin.com/in/alice"},
        ],
    )
    assert fetch_linkedin(object(), "alice") == "https://www.linkedin.com/in/alice"

    monkeypatch.setattr(ba, "_get_json", lambda *_a, **_k: None)
    assert fetch_linkedin(object(), "alice") == ""


# -- main(): end-to-end wiring with every network boundary stubbed ------------


def test_main_regenerates_yaml_and_audit(monkeypatch, tmp_path):
    """main() wires resolution to disk: it writes the curated YAML and the audit CSV."""
    monkeypatch.setattr(ba, "GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(ba, "shared_client", object)
    monkeypatch.setattr(ba, "SRC", tmp_path)
    monkeypatch.setattr(ba, "ORG_DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(ba, "ORG", "hiero-ledger")

    monkeypatch.setattr(ba, "fetch_governance_config", lambda *_a, **_k: {})
    monkeypatch.setattr(ba, "build_repo_role_lookup", lambda _c: {"repo": {"alice": "maintainer"}})
    monkeypatch.setattr(ba, "build_team_membership", lambda _c: {})
    monkeypatch.setattr(ba, "fetch_maintainers_affiliations", lambda _c: {})
    monkeypatch.setattr(ba, "gpg_uid_emails", lambda _login: [])
    monkeypatch.setattr(ba, "commit_author_org", lambda *_a, **_k: None)
    monkeypatch.setattr(ba, "fetch_linkedin", lambda *_a, **_k: "")
    monkeypatch.setattr(
        ba,
        "_fetch_profiles",
        lambda _client, people: [
            {"login": p, "name": p.title(), "company": "Hashgraph", "email": "", "bio": "", "orgs": []} for p in people
        ],
    )

    (tmp_path / "data").mkdir()
    ba.main()

    yaml_text = (tmp_path / "data" / "affiliations.yaml").read_text(encoding="utf-8")
    assert 'alice: "Hashgraph"' in yaml_text
    assert (tmp_path / "data" / "hiero-ledger" / "maintainer_affiliation_audit.csv").exists()


def test_main_requires_a_token(monkeypatch):
    """main() aborts loudly when GITHUB_TOKEN is absent rather than fetching nothing."""
    monkeypatch.setattr(ba, "GITHUB_TOKEN", None)
    with pytest.raises(SystemExit, match="GITHUB_TOKEN"):
        ba.main()
