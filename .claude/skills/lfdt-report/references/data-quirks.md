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
  still appear in `profiles`. Sort `profiles` by total activity, scan the
  top fifty logins for app-like names (`-app`, `-agent`, `-security`,
  `-quality`, `bot`), footnote any you find, and do not silently subtract
  them. Seen on 2026-10-06: `copilot-swe-agent`, `github-advanced-security`,
  `github-code-quality`, `stepsecurity-app`, and `testlens-app` (an
  organisation account). The "quiet teams" tile (3) was three single-member
  automation teams; say so if you cite it. Logins are not
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
- **Neither issue-queue document is the open backlog.** `issue-difficulty`
  "By repo" over-counts open issues (its incremental store never sees
  closures; 4,336 published against roughly 3,500 on GitHub on 2026-10-06);
  "Over time (weekly)" counts only issues created in the last 365 days
  (1,714). Describe the queue without a count and put both figures, with
  this explanation, in the Data notes. Report both with
  their variant titles (SKILL.md step 5, rule 5).
- **Roles held and roles active are not the same population.** The
  Governance tiles count people at their current highest role; the yearly
  active-by-role series attaches the role the actor held at the time. "80
  of 104 maintainers active in 2026" is therefore approximate; say so.
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

- **Governance "all time" is not all time.** The role-coverage base tables
  (`repoactivity`, `understaffed`, `loadshare`, `gonedark` all-time rows)
  use a 90-day activity window (hiero-hackers/analytics#413), which is why
  all-time `understaffed` (16) can be smaller than its `7d` table (26).
  Cite the `365d` period table and say so.

## Known disagreements between documents

Both sides go in the Data notes with their ids. When the gap is more than
about a tenth the body carries no number (SKILL.md step 5, rule 5); when
the two documents measure different things, say so and headline the
dashboard's figure.

- Repo count: `entities.repositories.count` (repos with tracked activity)
  vs the repo-level tables (`codeowners`, `release-staleness`,
  `repoactivity`) and `repo-growth` cumulative (every repo). Report the
  table count as the org size and the entity count as "repos with
  activity". On 2026-10-06 hiero-ledger was 42 vs 44 and hiero-hackers 24
  vs 28; name the missing repos from the documents in front of you, they
  change between runs. The repo-level tables are not all the same set
  either (governance-based ones include `roadmap` and lack
  `hiero-identity-standards`; CODEOWNERS and release tables the reverse),
  so "org size" is the count of the table you cite, named.
- Single-employer repos: not a disagreement but two definitions. The
  `repodiversity` table's `distinct_orgs == 1` (14 on 2026-10-06) counts
  repos with one named employer even when other seats are independents;
  the `org-diversity` "Single-employer repos by org" chart (9) excludes
  those. Headline the chart's figure as "single employer"; the table's is
  "one named employer".
- HIPs with merged evidence: the funnel and by-status charts exclude
  Deferred specs; filtering `hip-evidence` by `counted` (bool) and
  `pr_state == "MERGED"` (upper case) includes them (51 vs 53).
- Hashgraph, Hedera, The Hashgraph Association and Hashgraph Online are
  separate employers by policy (`docs/affiliations.md`; only Swirlds Labs
  folds into Hashgraph). Do not merge them, and do not call the split a
  defect; say in the Data notes that related entities are listed
  separately. A row whose employer is a role word ("contributor") is a
  mapping defect; note it.
- Single-employer teams: `teamdiversity` rows with `distinct_orgs == 1`
  (40 on 2026-10-06) vs the `org-diversity` "Single-employer teams by org"
  chart (27). The table carries a `single_employer` flag that matches the
  chart exactly; `derive.py single-employer` prints both readings and names
  the columns it used.
- Methodology text can be wrong about its own document: the yearly
  pipeline cites an "active at year end" variant that is not published,
  and the `affiliation_donut` methodology says only the two largest
  employers are kept while the document holds every employer (`top_n` 10
  is the display cut). Cite only what the manifest lists and the document
  holds; note the mismatch as a data defect.
- Repo ids are slugs: `.github` appears as `_github`.
