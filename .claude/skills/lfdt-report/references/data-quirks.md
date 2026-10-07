# Data quirks and known disagreements

Things that are true of this API and that a TAC reader would misread without
being told. Check each one every run; the dates say when they were last seen.

## Traps

- **"Adoption" means two different things.** The TAC's "adoption" is who uses
  the project (ADOPTERS.md). The HIPs "adoption funnel" is how far improvement
  proposals get implemented. Never use the funnel as evidence of adopters.
- **Unknown is not independent.** "Unknown" means no public signal could place
  the person; "independent" means no named employer. Report the affiliation
  known share (a metric tile) whenever you quote an organisation chart.
- **Counts are GitHub logins, bots excluded by a name rule.** The rule is
  `*[bot]`, `*-bot` and a short name list (`domain/bots.py`), so GitHub App
  accounts outside it (code-quality or security scanners, coding agents)
  still appear in `profiles`. Scan the top rows for obvious automation,
  footnote any you find, and do not silently subtract them. Logins are not
  people, and they will not match other tools' "authors" counts. Hiero's
  earlier reports cite LFX Insights authors and GitHub Actions metrics; never
  merge those with API numbers, and say which source a figure comes from if
  the maintainer keeps both.
- **Only some activity is tracked:** PRs opened, issues opened, reviews,
  merges and label changes. Comments and reactions are not, so activity is
  not discussion.
- **HIP evidence is evidence, not completion.** "No reference found" is absence
  of evidence. Only the Hiero era (since September 2024) is counted. The
  `hip-evidence` table is the PR-level backing for every HIP figure; the
  `hip-unknown` table lists PRs citing a HIP number that is not in the spec
  list, which is a data-quality caveat worth one line.
- **Two issue-queue documents disagree, by a lot.** `issue-difficulty` "By
  repo" is a snapshot of open issues per repo; "Over time (weekly)" is
  event-based. On 2026-10-06 they gave 4,336 and 1,714 open issues for
  hiero-ledger on the same day. Report both with
  their variant titles (SKILL.md step 5, rule 5).
- **TSC review counts are not published, but TSC activity is.** The
  `tscrepo` section (Governance) shows which repos TSC members work in and
  their role there. Cite it as the closest signal; it is activity, not dated
  review events.
- **Release staleness ranking** is dominated by repos that never ship a GitHub
  Release (docs, governance, meta). Do not call them neglected. Prereleases
  are plotted on the timeline but excluded from latest-release and pace.
- **Discord is a manual export**, published once under hiero-ledger, and
  silently ages. If it is absent or its date is old, it is a gap.
- **Chart PNGs were retired in autumn 2026.** Older docs and issues that list
  "PNG-only" data as a gap are out of date: check the chart documents first,
  because the data is probably there as JSON.
- **The API is `v1`, additive-only, and flagged `wip`.** Say so in the
  provenance block.

## Known disagreements between documents

Report both sides with their ids; never pick one silently.

- Repo count: `entities.repositories.count` (repos with tracked activity)
  vs the repo-level tables (`codeowners`, `release-staleness`,
  `repoactivity`) and `repo-growth` cumulative (every repo). Report the
  table count as the org size and the entity count as "repos with
  activity". On 2026-10-06 hiero-ledger was 42 vs 44 (missing from the
  entity index: `roadmap`, `solo-build-actions`); hiero-hackers 24 vs 28.
- Single-employer repos: the `repodiversity` table flags `distinct_orgs ==
  1` even when the other seats are independents; the `org-diversity`
  "Single-employer repos by org" chart excludes independents, so it shows
  fewer (14 vs 9 on 2026-10-06).
- HIPs with merged evidence: the funnel and by-status charts exclude
  Deferred specs; filtering `hip-evidence` by `counted` (bool) and
  `pr_state == "MERGED"` (upper case) includes them (51 vs 53).
- Employer names are not normalised: Hashgraph, Hedera, The Hashgraph
  Association and Hashgraph Online are separate rows, and a mapping error
  can surface as an employer literally named "contributor". Do not merge
  them; list them as a data defect in the appendix.
- Single-employer teams: `teamdiversity` rows with `distinct_orgs == 1`
  (40 on 2026-10-06) vs the `org-diversity` "Single-employer teams by org"
  chart (27), for the same independents reason as repos.
- Methodology text can be wrong about its own document: the yearly
  pipeline cites an "active at year end" variant that is not published,
  and the `affiliation_donut` methodology says only the two largest
  employers are kept while the document holds every employer (`top_n` 10
  is the display cut). Cite only what the manifest lists and the document
  holds; note the mismatch as a data defect.
- Repo ids are slugs: `.github` appears as `_github`.
