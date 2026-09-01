"""Shared column vocabulary — the prose behind each tab's "how to read this".

Definitions live here once so two tabs describing the same column cannot drift
apart; each family selects the entries its own columns actually use, via
:func:`glossary_of`, so a tab never explains columns it does not show.

Pure data: the web dashboard renders it. Definitions may mark emphasis with
``*asterisks*`` (rendered as ``<em>``); no other markup.
"""

from __future__ import annotations

GLOSSARY_TITLE = "How to read this — what each column means"

# term -> definition. Keys are the column labels as they appear in the tables
# (several labels share one entry where the column is named differently by
# audience, e.g. "contributor / account / member / user").
TERMS: dict[str, str] = {
    "contributor / account / member / user": "a GitHub login.",
    "PRs": "pull requests this person opened (authored).",
    "reviews": "pull-request reviews they submitted on any PR.",
    "merges": "pull requests they merged (clicked ‘merge’).",
    "issues": "issues they opened.",
    "labels": "label add/remove actions they performed (triage).",
    "actions": (
        "PRs + reviews + merges + issues + labels, summed — one activity total. "
        "“maint./comm. actions” split it by the repo’s maintainers / committers / triage."
    ),
    "review+merge": (
        "reviews submitted + PRs merged, summed — the “shepherding” load. "
        "Both committers and maintainers can merge (triage cannot)."
    ),
    "mergers": "how many people (committers + maintainers) reviewed or merged in the repo.",
    "top carrier / top % / top role": (
        "the person doing the most review+merge in a repo, their share of it (top-2 % = the top two "
        "combined), and whether they are a committer or maintainer."
    ),
    "period tabs": (
        "activity counts and active / quiet status use the selected rolling period; "
        "All time includes every tracked event."
    ),
    "repos": "number of distinct repositories they were active in.",
    "last active": "date of their most recent tracked activity (all-time).",
    "status": (
        "in activity tables: *active* = recent activity within the window, *quiet* = none in it. "
        "In the affiliations table: *affiliated* / *independent* / *unknown* — whether the person "
        "maps to a named employer."
    ),
    "days since active": "days since their most recent activity (all-time; blank = never active).",
    "role / role here": (
        "governance permission in that repo: triage, committer, or maintainer; *general* = holds no special role there."
    ),
    "maintainers / committers / triage": (
        "as a count column (Repository activity), the number of people holding that role in the repo."
    ),
    "members": "the number of people on the team.",
    "active / members active": (
        "how many of the group (team members, role-holders) had activity in the window — vs. the total."
    ),
    "highest role": "the most senior role a person holds in any repo (maintainer > committer > triage).",
    "roles held": "every distinct role the person holds across repos.",
    "how roles are set": (
        "a person’s role in a repo comes from the governance config’s team→permission grants: "
        "*triage* → triage, *write* → committer, *maintain* / *admin* → maintainer "
        "(*read* access isn’t counted). Where someone holds more than one, the highest is shown."
    ),
    "org-wide teams": (
        "a few teams (github-maintainers, security-maintainers, lf-staff, tsc, hiero-triage) are granted "
        "on nearly every repo. To keep each repo’s domain maintainers visible, these are not counted "
        "on domain repos; they’re credited only on org/meta repos (e.g. .github, governance) that have "
        "no domain maintainer team of their own. So members of those teams appear on just those few repos."
    ),
    # --- Affiliation and organisation-diversity columns -------------------
    "organisation": (
        "the employer a person was mapped to from public signals (GPG key email, profile, MAINTAINERS.md, "
        "company field, org membership). Never inferred from a personal email domain."
    ),
    "method": (
        "how the mapping was decided: *automated* (the resolver placed them from public signals) or "
        "*manual* (a hand-correction in affiliations.yaml, which survives regeneration)."
    ),
    "resolved": "how many of the group could be mapped to a named employer at all.",
    "distinct orgs": (
        "how many different employers the resolved people span. A value of 1 means one employer holds "
        "every seat — an organisational bus-factor."
    ),
    "largest org / largest org %": (
        "the employer holding the most seats, and its share of the *resolved* people (not of everyone — "
        "unknowns are excluded from the denominator)."
    ),
    "HHI": (
        "Herfindahl-Hirschman Index of employer concentration, 0–10000; 10000 means a single employer "
        "holds every resolved seat. Higher is more concentrated."
    ),
    "single employer": "flagged when one employer holds every resolved seat — a capture / bus-factor risk.",
    "independent": (
        "people with no named employer: solo contributors, or personal-email-only signals. They count towards "
        "the resolved population, but they are not an employer, so the diversity pie pools them into 'Other' "
        "instead of ranking them against real organisations; the per-repo mix chart and the diversity "
        "tables still break them out on their own."
    ),
    "unknown": (
        "people no public signal could place. Not the same as independent — it means *we could not tell*, "
        "so they are excluded from the share and concentration calculations rather than counted as solo. "
        "They remain visible as unknown rows in the affiliations and diversity tables, while the affiliation "
        "coverage log and warning track how much of each role population is known."
    ),
    "committer": (
        "in the committer affiliations table, a person whose *highest* role anywhere is committer — write "
        "access in at least one repository and a maintainer seat in none. Disjoint from the maintainer "
        "table by construction, so the two role tabs never count the same person twice."
    ),
    "role tabs": (
        "on the organisation-diversity charts, whether you are looking at maintainers or committers. The "
        "two populations are disjoint (each person counts at their highest role), so the committer tab is "
        "the bench beneath the maintainers — if it spans more employers than the maintainer tab, diversity "
        "is more likely to improve as people are promoted. Curation is thinner for committers, so read its "
        "unknown rows and known share before drawing conclusions. The team charts have no role tabs: "
        "team membership is not a permission."
    ),
    "organisation mix": "the employers present in the group, largest first.",
}

GLOSSARY_NOTE = (
    "Tabbed activity tables use the selected period; reference tables labelled “all-time” are "
    "cumulative. The permission-holder cleanup list uses a fixed 180-day quiet threshold. Tracked "
    "activities are opening PRs/issues, reviewing, merging, and labeling — comments and reactions "
    "are not counted."
)


def glossary_of(keys: tuple[str, ...], *, title: str = GLOSSARY_TITLE, note: str | None = None) -> dict:
    """Build a tab's column glossary from selected shared terms, in the given order.

    Raises on an unknown key so a renamed term fails loudly here rather than
    silently dropping a definition from a tab.
    """
    unknown = [key for key in keys if key not in TERMS]
    if unknown:
        raise KeyError(f"unknown glossary term(s): {unknown}")
    glossary: dict = {
        "title": title,
        "layout": "definitions",
        "terms": [{"term": key, "definition": TERMS[key]} for key in keys],
    }
    if note:
        glossary["note"] = note
    return glossary
