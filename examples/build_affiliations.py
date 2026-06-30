"""Regenerate ``src/hiero_analytics/data/affiliations.yaml`` from public signals.

Resolves every governance participant — maintainers, committers, triage, and all
``config.yml`` team members — to an organisation, using, in precedence order:

  1. GPG-key UID email      (github.com/<login>.gpg; what they actively sign with)
  2. profile email
  3. MAINTAINERS.md          ('Company Affiliation' column, self-declared)
  4. GitHub company field
  5. public org membership
  6. solo-domain             (only a *curated* small-company domain -> a named org)
  7. commit-author email      (last-resort backup, mined from the commit API)

Obfuscated ``users.noreply.github.com`` addresses never count — they tell us
nothing. A bio with several ``@`` mentions is treated as interests, not an
employer. A current external company (e.g. Robinhood) outranks stale ecosystem
signals. LinkedIn links are surfaced in the audit for manual follow-up only;
LinkedIn is never scraped. Lineage: Swirlds Labs was renamed to Hashgraph.

This is a maintenance tool, NOT part of the dashboard pipeline (which just reads
the curated YAML offline). It needs network access, a ``GITHUB_TOKEN``, and the
``gpg`` CLI. Run from the repo root:

    GITHUB_TOKEN=... uv run python examples/build_affiliations.py

It writes the curated YAML and a gitignored provenance audit CSV. The YAML is the
source of truth: hand-edit it afterwards (e.g. for people no signal can place).
"""

from __future__ import annotations

import base64
import csv
import json
import os
import re
import subprocess
import time
from collections import Counter
from urllib.parse import urlparse

import requests

from hiero_analytics.config.paths import ORG, ORG_DATA_DIR, SRC
from hiero_analytics.data_sources.governance_config import (
    build_repo_role_lookup,
    build_team_membership,
    fetch_governance_config,
)
from hiero_analytics.domain.bots import is_bot_login

ORGS = ("hiero-ledger", "hiero-hackers")
NOREPLY = "users.noreply.github.com"
EMAIL_RE = re.compile(r"<([^<>@\s]+@[^<>\s]+)>")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"}

# --- entity maps (each a distinct entity; Swirlds Labs folded into Hashgraph) ---
EMAIL_DOMAIN = {
    "swirldslabs.com": "Hashgraph", "swirlds.com": "Hashgraph", "hashgraph.com": "Hashgraph",
    "hedera.com": "Hedera", "hgraph.com": "Hgraph", "limechain.tech": "LimeChain",
    "limehcain.tech": "LimeChain", "openelements.com": "OpenElements",
    "open-elements.com": "OpenElements", "dsr-corporation.com": "DSR Corporation",
    "linuxfoundation.org": "Linux Foundation", "blockydevs.com": "BlockyDevs",
    "launchbadge.com": "Launchbadge",
}
COMPANY_FULL = {
    # 'Hedera Hashgraph LLC' is the old unified company name (ancestor of both the
    # Hashgraph engineering company and the Hedera network entity); on its own it
    # means the Hedera side. Actual Hashgraph staff resolve via their work email.
    "hedera hashgraph llc": "Hedera", "hedera hashgraph": "Hedera", "swirlds labs": "Hashgraph",
    "the hashgraph association (tha)": "The Hashgraph Association",
    "the hashgraph association": "The Hashgraph Association", "hashgraph-association": "The Hashgraph Association",
    "the linux foundation": "Linux Foundation", "linux foundation": "Linux Foundation",
    "dsr corporation": "DSR Corporation", "open elements gmbh": "OpenElements",
    "turtle moon llc": "Turtle Moon", "jitty labs": "Jitty Labs", "guy who builds for fun": None,
}
COMPANY_TOKEN = {
    "hashgraph": "Hashgraph", "swirlds": "Hashgraph", "swirldslabs": "Hashgraph", "hgraph": "Hgraph",
    "hedera": "Hedera", "openelements": "OpenElements", "limechain": "LimeChain",
    "linuxfoundation": "Linux Foundation", "launchbadge": "Launchbadge", "blockydevs": "BlockyDevs",
    "dsr": "DSR Corporation",
}
EMPLOYER_ORG = {
    "hashgraph": "Hashgraph", "swirldslabs": "Hashgraph", "swirlds": "Hashgraph",
    "openelements": "OpenElements", "hashgraph-association": "The Hashgraph Association",
    "limechain": "LimeChain",
}
SMALL_ORG_NAME = {
    "devlabs.bg": "DevLabs", "goodmorning.dev": "DevLabs", "onepiece.software": "Onepiece Software",
    "gradle.com": "Gradle", "8bees.fr": "8bees", "capsule03.com": "Capsule03", "sydor.dev": "Sydor",
    "labeltech.io": "LabelTech", "jcovalent.com": "JCovalent", "servercurio.com": "ServerCurio",
    "zkbricks.com": "zkBricks", "retrove.io": "Retrove", "pandaswhocode.com": "Pandas Who Code",
}
SMALL_ORG_FROM_COMPANY = {"hol": "Hashgraph Online"}
SMALL_ORG_FROM_ORG = {"hashgraph-online": "Hashgraph Online"}
_MD_COMPANY = {
    "hashpack": "HashPack", "onepiece": "Onepiece Software", "8bees": "8bees",
    "capsule03": "Capsule03", "turtlemoon": "Turtle Moon", "hol": "Hashgraph Online",
}
_MD_COMPANY_FULL = {
    "hashgraph online": "Hashgraph Online", "open elements": "OpenElements",
    "hedera foundation": "Hedera", "turtle moon": "Turtle Moon", "milanwr.com (8bees)": "8bees",
}
_PERSONAL = {
    "gmail.com", NOREPLY, "outlook.com", "hotmail.com", "icloud.com", "proton.me", "protonmail.com",
    "web.de", "yahoo.com", "qq.com", "abv.bg", "pacbell.net", "news.co.uk",
}
_MD_SKIP = {"", "-", "n/a", "none", "tbd"}
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")


def get(url: str, params: dict | None = None) -> requests.Response | None:
    """GET with a basic secondary-rate-limit backoff; ``None`` on non-200."""
    for _ in range(4):
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
        except requests.RequestException:
            return None
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            time.sleep(20)
            continue
        return resp if resp.status_code == 200 else None
    return None


def email_domain(addr: str) -> str:
    """The domain part only ('@gmail.com'). Used so a full email address is never
    written to disk — resolution uses the full address in memory; the audit logs
    only the domain."""
    addr = (addr or "").strip()
    return "@" + addr.split("@", 1)[1] if "@" in addr else ""


# Cells that begin with one of these can run as a formula when the CSV is opened in
# Excel / Google Sheets (CSV injection). Several audit columns carry attacker-controlled
# GitHub fields (name, company, bio, email domain, LinkedIn URL), so neutralise them.
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value: object) -> object:
    """Prefix a formula-triggering cell with ' so spreadsheets treat it as text.

    The lone '-' placeholder used for empty fields is left alone (a bare hyphen is
    not a formula) so the audit stays readable.
    """
    text = str(value)
    if text and text != "-" and text[0] in _CSV_FORMULA_PREFIXES:
        return "'" + text
    return value


def org_from_email(raw: str) -> str | None:
    if not raw or "@" not in raw:
        return None
    domain = raw.split("@")[-1].strip().lower()
    return None if domain in _PERSONAL else EMAIL_DOMAIN.get(domain)


# Company-field values that aren't an employer (so they don't become a named org).
_COMPANY_JUNK = {
    "", "-", "n/a", "none", "self", "self employed", "self-employed", "freelance", "freelancer",
    "freelancing", "independent", "me", "myself", "open source", "opensource", "various", "remote",
    "home", "world", "earth", "internet", "the internet", "student", "unemployed", "looking",
    "open to work", "none of your business", "stealth mode startup", "stealth", "stealth startup",
    "blog", "live", "crypto", "web3", "blockchain",
}
_COMPANY_NOT_EMPLOYER = {"hiero-ledger", "hiero-hackers", "hiero", "lf-decentralized-trust"}


def org_from_company(raw: str) -> str | None:
    """Map the company field to a known *ecosystem* org (None if not one of them)."""
    if not raw:
        return None
    norm = raw.strip().lower()
    if norm in COMPANY_FULL:
        return COMPANY_FULL[norm]
    for token in (t.lstrip("@") for t in norm.replace(",", " ").split()):
        if token in COMPANY_TOKEN:
            return COMPANY_TOKEN[token]
    return None


def external_company(raw: str) -> str | None:
    """A real *external* employer named in the company field (e.g. 'Robinhood').

    Used so a current external employer outranks stale ecosystem signals (an old
    commit email, a lapsed org membership). Junk, project handles, multi-handle
    'interest' lists, and free-text sentences are rejected.
    """
    if not raw or raw.count("@") > 1:
        return None
    name = raw.strip().lstrip("@").strip()
    low = name.lower()
    if not name or low in _COMPANY_JUNK or low in _COMPANY_NOT_EMPLOYER:
        return None
    if not any(ch.isalpha() for ch in name) or len(name.split()) > 3:
        return None
    return name


def orgs_from_membership(orgs: list[str]) -> set[str]:
    return {EMPLOYER_ORG[o.lower()] for o in orgs if o.lower() in EMPLOYER_ORG}


def load_manual_overrides(path) -> dict[str, tuple[str, str]]:
    """Read the existing YAML; return ``{login: (value, reason)}`` for hand-corrected rows.

    Manual corrections survive regeneration: edit a row's value and append
    ``# manual`` (or ``# manual: reason``). On the next run the generator keeps
    that value verbatim and re-flags it, instead of overwriting it from signals.
    """
    overrides: dict[str, tuple[str, str]] = {}
    if not path.exists():
        return overrides
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.lstrip().startswith("#") or ":" not in raw:
            continue
        body, sep, comment = raw.partition("#")
        # 'manual' anywhere in the comment — the generator's '… · MANUAL — …', a fresh
        # '# manual[: reason]', or one appended after the role tag ('# maintainer # manual').
        is_manual = bool(re.search(r"\bmanual\b", comment, re.IGNORECASE))
        if not sep or not is_manual:
            continue
        login, _, value = body.partition(":")
        keyword = re.search(r"(?i)\bmanual\b\s*[:\-—·]?\s*", comment)
        reason = comment[keyword.end():] if keyword else ""
        reason = re.sub(r"\s*\(resolver:.*\)\s*$", "", reason).strip()
        overrides[login.strip().lower()] = (value.strip().strip('"').strip(), reason)
    return overrides


def org_from_bio(bio: str) -> str | None:
    """Employer from an '@ Company' mention in the profile bio (e.g. 'Dev rel @ Hashgraph').

    Only '@'-prefixed handles are matched, so a casual mention of a company name
    in prose doesn't create a false positive.
    """
    if not bio:
        return None
    mentions = re.findall(r"@\s?([a-z0-9-]+)", bio.lower())
    # Several @ mentions read as interests / communities, not an employer.
    if len(mentions) != 1:
        return None
    token = mentions[0]
    return COMPANY_TOKEN.get(token) or EMPLOYER_ORG.get(token)


def derive_small_org(gpg_emails: list[str], email: str, company: str, orgs: list[str]) -> str | None:
    """A *curated* small / solo org from a known brand domain or the company/org maps.

    Deliberately conservative: an uncurated personal domain (often just someone's
    own name, e.g. nickpoorman.com) is NOT minted into an org — those people stay
    Independent. Add genuine small consultancies to SMALL_ORG_NAME by hand.
    """
    for addr in [*gpg_emails, *([email] if email else [])]:
        domain = addr.split("@")[-1].strip().lower()
        if domain in SMALL_ORG_NAME:
            return SMALL_ORG_NAME[domain]
    comp = company.strip().lower().lstrip("@")
    if comp in SMALL_ORG_FROM_COMPANY:
        return SMALL_ORG_FROM_COMPANY[comp]
    for org in orgs:
        if org.lower() in SMALL_ORG_FROM_ORG:
            return SMALL_ORG_FROM_ORG[org.lower()]
    return None


def gpg_uid_emails(login: str) -> list[str]:
    """UID emails from the login's published public GPG key(s)."""
    try:
        resp = requests.get(f"https://github.com/{login}.gpg", timeout=15)
    except requests.RequestException:
        return []
    if resp.status_code != 200 or "BEGIN PGP" not in resp.text:
        return []
    try:
        out = subprocess.run(
            ["gpg", "--show-keys", "--with-colons"],
            input=resp.text, capture_output=True, text=True, timeout=15, check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found = {m.group(1).lower() for row in out.splitlines()
             if row.startswith("uid:") and (m := EMAIL_RE.search(row))}
    return sorted(found)


def org_from_md_company(raw: str) -> str | None:
    norm = raw.strip().lower()
    if norm in _MD_SKIP:
        return None
    if norm in _MD_COMPANY_FULL:
        return _MD_COMPANY_FULL[norm]
    if norm in COMPANY_FULL:
        return COMPANY_FULL[norm]
    for token in re.findall(r"[a-z0-9]+", norm):
        if token in _MD_COMPANY:
            return _MD_COMPANY[token]
        if token in COMPANY_TOKEN:
            return COMPANY_TOKEN[token]
    return None


def parse_maintainers_md(md: str):
    """Yield ``(github_id_lower, raw_company)`` from every pipe table with a GitHub column."""
    cols = None
    for line in md.splitlines():
        if not line.strip().startswith("|"):
            cols = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        low = [c.lower() for c in cells]
        if any("github" in c for c in low):
            cols = low
            continue
        if cols is None or set("".join(cells)) <= set("-: "):
            continue
        gi = next((i for i, c in enumerate(cols) if "github" in c), None)
        ci = next((i for i, c in enumerate(cols)
                   if any(k in c for k in ("company", "affiliation", "organization"))), None)
        if gi is None or gi >= len(cells):
            continue
        gid = _MD_LINK.sub(r"\1", cells[gi]).strip().strip("@ ").lower()
        company = cells[ci] if ci is not None and ci < len(cells) else ""
        if gid:
            yield gid, company


def fetch_maintainers_affiliations() -> dict[str, str]:
    """Build ``{github_id -> declared org}`` from every repo's MAINTAINERS.md."""
    declared: dict[str, set[str]] = {}
    for org in ORGS:
        page, repos = 1, []
        while True:
            resp = get(f"https://api.github.com/orgs/{org}/repos",
                       params={"per_page": 100, "page": page, "type": "public"})
            if not resp or not resp.json():
                break
            repos += [x["name"] for x in resp.json()]
            page += 1
        for repo in repos:
            md = None
            for fname in ("MAINTAINERS.md", "MAINTAINERS"):
                resp = get(f"https://api.github.com/repos/{org}/{repo}/contents/{fname}")
                if resp:
                    md = base64.b64decode(resp.json()["content"]).decode("utf-8", "replace")
                    break
            if not md:
                continue
            for gid, company in parse_maintainers_md(md):
                org_name = org_from_md_company(company)
                if org_name:
                    declared.setdefault(gid, set()).add(org_name)
    return {gid: next(iter(orgs)) for gid, orgs in declared.items() if len(orgs) == 1}


def commit_author_org(login: str) -> str | None:
    """Backup: the most common employer domain among the login's signed-out commits.

    Mined from the commit search API (no clone). Obfuscated noreply emails never
    map, so this only resolves people who committed with a real employer email.
    """
    counts: Counter[str] = Counter()
    for org in ORGS:
        resp = get("https://api.github.com/search/commits",
                   params={"q": f"author:{login} org:{org}", "per_page": 30})
        if not resp:
            continue
        for item in resp.json().get("items", []):
            email = (item.get("commit", {}).get("author") or {}).get("email", "")
            org_name = org_from_email(email)
            if org_name:
                counts[org_name] += 1
    return counts.most_common(1)[0][0] if counts else None


def fetch_linkedin(login: str) -> str:
    """The login's LinkedIn URL, if linked on their profile (manual pointer only)."""
    resp = get(f"https://api.github.com/users/{login}/social_accounts")
    if not resp:
        return ""
    for acct in resp.json():
        url = acct.get("url", "")
        host = (urlparse(url).hostname or "").lower()
        if acct.get("provider") == "linkedin" or host == "linkedin.com" or host.endswith(".linkedin.com"):
            return url
    return ""


def main() -> None:
    if not TOKEN:
        raise SystemExit("GITHUB_TOKEN is required")

    yaml_path = SRC / "data" / "affiliations.yaml"
    manual_overrides = load_manual_overrides(yaml_path)
    print(f"manual overrides found: {len(manual_overrides)}")

    config = fetch_governance_config()
    role_lookup = build_repo_role_lookup(config)
    team_membership = build_team_membership(config)

    # Every governance participant, not just maintainers, so team/repo concentration
    # is measured against the whole population. Bots are excluded.
    people = {u for holders in role_lookup.values() for u in holders}
    people |= {m for members in team_membership.values() for m in members}
    people = sorted(p for p in people if not is_bot_login(p))
    maintainers = {u for holders in role_lookup.values() for u, r in holders.items() if r == "maintainer"}
    print(f"governance participants: {len(people)} ({len(maintainers)} maintainers)")

    # Highest governance role per login, annotated on each YAML row for clarity.
    role_of: dict[str, set[str]] = {}
    for holders in role_lookup.values():
        for login, role in holders.items():
            role_of.setdefault(login.lower(), set()).add(role)

    def scope_of(login: str) -> str:
        held = role_of.get(login.lower(), set())
        for role in ("maintainer", "committer", "triage"):
            if role in held:
                return role
        return "team"

    md_declared = fetch_maintainers_affiliations()
    print(f"MAINTAINERS.md: {len(md_declared)} handles with a resolved declared company")

    # Profile fields in batches via GraphQL.
    from hiero_analytics.data_sources.github_client import GitHubClient
    client = GitHubClient()
    rows = []
    for i in range(0, len(people), 20):
        batch = people[i : i + 20]
        parts = [
            f"u{j}: user(login: {json.dumps(login)}) {{ login name company email bio "
            f"organizations(first: 12) {{ nodes {{ login }} }} }}"
            for j, login in enumerate(batch)
        ]
        payload = (client.graphql("query {\n" + "\n".join(parts) + "\n}", {}).get("data")) or {}
        for j, login in enumerate(batch):
            node = payload.get(f"u{j}") or {}
            rows.append({
                "login": login,
                "name": (node.get("name") or "").strip(),
                "company": (node.get("company") or "").strip(),
                "email": (node.get("email") or "").strip(),
                "bio": (node.get("bio") or "").strip(),
                "orgs": [o["login"] for o in (node.get("organizations", {}) or {}).get("nodes") or []],
            })

    for r in rows:
        gpg_emails = gpg_uid_emails(r["login"])
        r["gpg_emails"] = gpg_emails
        gpg_orgs = {o for e in gpg_emails if (o := org_from_email(e))}
        if "Hashgraph" in gpg_orgs:
            gpg_orgs.discard("Hedera")  # @hedera.com is the predecessor-company alias
        g = next(iter(gpg_orgs)) if len(gpg_orgs) == 1 else None

        e = org_from_email(r["email"])
        md = md_declared.get(r["login"].lower())
        # The company field resolves to an ecosystem org or, failing that, the
        # external employer it names — either way it outranks bio / stale commits.
        c = org_from_company(r["company"]) or external_company(r["company"])
        bio = org_from_bio(r["bio"])
        org_set = orgs_from_membership(r["orgs"])
        o = next(iter(org_set)) if len(org_set) == 1 else None

        resolved = g or e or md or c or bio or o
        small = None if resolved else derive_small_org(gpg_emails, r["email"], r["company"], r["orgs"])
        resolved = resolved or small

        # Last-resort backup: mine commit-author emails only when nothing else placed them.
        commit_org = None
        if not resolved:
            commit_org = commit_author_org(r["login"])
            resolved = commit_org

        # Obfuscated noreply addresses are not an identity signal.
        real_gpg = [a for a in gpg_emails if not a.lower().endswith("@" + NOREPLY)]
        real_email = bool(r["email"]) and not r["email"].lower().endswith("@" + NOREPLY)
        has_identity = bool(real_gpg) or real_email or bool(r["company"])

        # Surface a LinkedIn pointer only where we still couldn't place them.
        r["linkedin"] = fetch_linkedin(r["login"]) if not resolved and not has_identity else ""

        if resolved:
            status = "affiliated"
        elif has_identity:
            status = "independent"
        else:
            status = "unknown"

        signals = {"gpg": g, "email": e, "maintainers_md": md, "company": c, "bio": bio,
                   "org": o, "small": small, "commit": commit_org}
        present = {k: v for k, v in signals.items() if v}
        agree = sum(1 for v in present.values() if v == resolved)
        r.update({
            "status": status, "resolved": resolved, "sources": sorted(present),
            "confidence": "verified" if agree >= 2 else ("single" if resolved else status),
            "gpg_org": g, "email_org": e, "maintainers_md_org": md, "company_org": c,
            "bio_org": bio, "org_membership_org": o, "small_org": small, "commit_email_org": commit_org,
        })
        if g and resolved == g:
            r["decided_by"] = "gpg-key email"
        elif e and resolved == e:
            r["decided_by"] = "profile email"
        elif md and resolved == md:
            r["decided_by"] = "MAINTAINERS.md"
        elif c and resolved == c:
            r["decided_by"] = "company field"
        elif bio and resolved == bio:
            r["decided_by"] = "profile bio"
        elif o and resolved == o:
            r["decided_by"] = "org membership"
        elif small and resolved == small:
            r["decided_by"] = "small/solo domain"
        elif commit_org and resolved == commit_org:
            r["decided_by"] = "commit email"
        elif status == "independent":
            r["decided_by"] = "personal email only"
        elif gpg_emails or r["email"]:
            r["decided_by"] = "obfuscated email only"
        else:
            r["decided_by"] = "no public signal"

        # A hand-correction wins over every signal, and is recorded so it stands out.
        r["auto_resolved"] = r["resolved"]
        r["auto_status"] = r["status"]
        override = manual_overrides.get(r["login"].lower())
        r["manual"] = bool(override)
        r["manual_reason"] = ""
        if override:
            value, reason = override
            r["manual_reason"] = reason
            if value in ("", "?"):
                r["status"], r["resolved"] = "unknown", None
            elif value.lower() == "independent":
                r["status"], r["resolved"] = "independent", None
            else:
                r["status"], r["resolved"] = "affiliated", value
            r["decided_by"] = "manual override"

    by_status = Counter(r["status"] for r in rows)
    print(f"affiliated {by_status['affiliated']}, independent {by_status['independent']}, "
          f"unknown {by_status['unknown']} of {len(rows)}")

    # Curated YAML (source of truth), keyed by login with the name as a comment.
    header = (
        "# Maintainer / governance participant -> organisation, for the diversity charts.\n"
        "# Regenerate with examples/build_affiliations.py. Seeded from public signals\n"
        "# (GPG-key email, profile email, MAINTAINERS.md, company field, profile bio,\n"
        "# org membership, solo domain, commit-author email), in that precedence.\n"
        "# Obfuscated noreply addresses never count. Lineage: Swirlds Labs was renamed\n"
        "# to Hashgraph; Hedera and Hgraph stay separate.\n#\n"
        '# Values: an organisation name | "Independent" (solo / personal-email only) |\n'
        '# "?" (unknown — no public signal).\n#\n'
        "# Each row's comment is 'governance-role · name' (maintainer | committer |\n"
        "# triage | team). Only the 104 maintainers feed the maintainer-org charts;\n"
        "# the rest are here so the team-concentration view is fully covered.\n#\n"
        "# TO HAND-CORRECT a row so it STANDS OUT and survives regeneration: change the\n"
        "# value and append '# manual' (or '# manual: your reason'). It is re-flagged\n"
        "# below as 'MANUAL' with the resolver's competing guess, and never overwritten.\n\n"
    )

    def yaml_value(r: dict) -> str:
        if r["status"] == "affiliated":
            return r["resolved"]
        return "Independent" if r["status"] == "independent" else "?"

    manual_count = sum(1 for r in rows if r["manual"])
    with yaml_path.open("w", encoding="utf-8") as f:
        f.write(header)
        for r in sorted(rows, key=lambda x: x["login"].lower()):
            scope = scope_of(r["login"])
            if r["manual"]:
                auto = r["auto_resolved"] or ("Independent" if r["auto_status"] == "independent" else "?")
                note = r["manual_reason"] or r["name"] or "corrected by hand"
                comment = f"  # {scope} · MANUAL — {note} (resolver: {auto})"
            else:
                comment = f"  # {scope} · {r['name']}" if r["name"] else f"  # {scope}"
            f.write(f"{r['login']}: {json.dumps(yaml_value(r), ensure_ascii=False)}{comment}\n")
    print(f"wrote {yaml_path} ({manual_count} manual overrides preserved)")

    # Provenance audit (gitignored — contains emails).
    audit_dir = ORG_DATA_DIR / ORG
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_path = audit_dir / "maintainer_affiliation_audit.csv"
    with audit_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "login", "name", "status", "affiliation", "decided_by", "confidence", "agreeing_signals",
            "gpg_emails", "gpg_org", "profile_email", "email_org", "maintainers_md_org",
            "company", "company_org", "bio_org", "public_orgs", "org_membership_org",
            "small_org_guess", "commit_email_org", "linkedin",
        ])
        for r in sorted(rows, key=lambda x: (x["status"], (x["resolved"] or "~"), x["login"].lower())):
            affiliation = r["resolved"] or ("Independent" if r["status"] == "independent" else "?")
            row = [
                r["login"], r["name"], r["status"], affiliation, r["decided_by"], r["confidence"],
                ";".join(r["sources"]) or "-",
                # Emails are redacted to their domain only — never the full address.
                ";".join(email_domain(e) for e in r["gpg_emails"]) or "-", r["gpg_org"] or "-",
                email_domain(r["email"]) or "-", r["email_org"] or "-", r["maintainers_md_org"] or "-",
                r["company"] or "-", r["company_org"] or "-", r["bio_org"] or "-",
                ";".join(r["orgs"]) or "-", r["org_membership_org"] or "-", r["small_org"] or "-",
                r["commit_email_org"] or "-", r["linkedin"] or "-",
            ]
            # Neutralise spreadsheet formula injection from attacker-controlled GitHub fields.
            w.writerow([csv_safe(cell) for cell in row])
    print(f"wrote {audit_path}")


if __name__ == "__main__":
    main()
