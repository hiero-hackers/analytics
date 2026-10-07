---
name: lfdt-report
description: Draft Hiero's LF Decentralized Trust TAC report (annual review or mid-year update) from this repo's published data API. Data-backed sections get real, cited numbers; judgment sections become marked maintainer slots; a Data Gaps appendix lists what the TAC asks for that the API cannot yet supply. Use whenever asked to write, draft, refresh, or prepare the LFDT / TAC annual review or mid-year report for hiero-ledger or any other org in the manifest.
---

# Drafting the LFDT TAC report

Hiero files two reports a year with the LFDT Technical Advisory Council (TAC):
an annual review and a mid-year update. Part of each is measurable (activity,
diversity, releases, security posture) and part is judgment (goals, help
needed, lifecycle recommendation). This skill fills the measurable part from
the data API with cited numbers, leaves the judgment part as marked slots for
maintainers, and lists everything the TAC wants that the API cannot supply.

The gap list is as much the product as the draft. It is how we learn what the
API layer is missing, and it is the input for follow-up issues.

This skill is documentation only. It never changes code, pipelines, or the API
contract. A gap is reported, not fixed.

## 1. Settle the inputs

- **Report type:** `annual` or `mid-year`. If the request does not say, ask.
  Never guess; the two have different questions and different periods.
- **Org:** default `hiero-ledger`. Any org in the manifest works. Others
  (e.g. `hiero-hackers`) are sparse by design, and that is a case to handle,
  not an error (see section 3).
- **Period:** annual covers the previous calendar year; mid-year covers the six
  months since the annual review. State the period in the draft header.
- **Prior report (optional):** a URL or file for the last report, so goals can
  be compared. If none is given, the goals slot says so. Do not go hunting.

## 2. Read the TAC instructions again, every run

Fetch both pages. They define the questions, and they change (mid-year
reports became mandatory in 2026):

- Annual: <https://lf-decentralized-trust.github.io/governance/project-updates/annual-review-instructions/>
- Mid-year: <https://lf-decentralized-trust.github.io/governance/project-updates/mid-year-update-instructions/>

`references/report-structure.md` holds a snapshot of both, plus the template.
If a live page differs from the snapshot, **the live page wins**: follow it, and
note in the appendix what changed. If the fetch fails, use the snapshot and say
so in the appendix.

## 3. Discover the data. Never assume it.

The API is static JSON, so no auth and no queries. Fetch the manifest first:

```bash
BASE=https://hiero-hackers.github.io/analytics/data/api/v1
curl -s $BASE/manifest.json -o /tmp/manifest.json
python3 - <<'PY'
import json
m = json.load(open('/tmp/manifest.json'))
print(m['version'], 'wip=', m.get('wip'), m['generated_at'], m['provenance'])
print('orgs:', list(m['orgs']))
PY
```

If the dashboard was generated locally, the same files are under
`outputs/data/api/v1/`; use that only when the maintainer says to work offline.

Rules while reading the manifest:

- **Record provenance first:** `generated_at`, `provenance.git_sha`,
  `provenance.data_as_of`, and whether `wip` is true. All of it goes in the
  appendix. `data_as_of` is the oldest dataset watermark, so it is the honest
  "data as of" date for the whole report.
- **Org not in `orgs`:** stop and list the orgs that are. Do not draft.
- **Sections and chart sections:** read them from
  `orgs[org].sections`, `orgs[org].chart_sections`, `orgs[org].views` and
  `orgs[org].metrics`. Do not hard-code section ids; resolve them by `macro`
  and `id` from the manifest in front of you. `references/api-section-map.md`
  says which ones answer which TAC question.
- **`row_count` of 0:** that is a gap ("no rows"), never a measured zero.
- **`absorbed_by`:** the section is a role variant that another card now
  renders as a tab. Do not report it as a separate section; read its rows as
  variants of the absorbing section.
- **A macro missing for the org:** `macro_absent_notes[macro]` says why.
  Quote that note verbatim in the appendix. An ungoverned org has no role
  data; write "role data is not available for this org", never "no
  maintainers".
- **Chart documents** live at `charts[].variants[].interactive.path`. Their
  `kind` (`timeseries`, `categories`, `matrix`, `network`, `events`) decides
  how to read them. `web/src/api.ts` documents every shape; read it, do not
  guess field names.

## 4. Read what the API says about itself, then the numbers

For every document you cite, read its own `note`, `methodology`, `population`,
`window`, `stale` and `generated_at` before using a number. Those are the
definitions a TAC reader needs, and they are the only reliable statement of who
was counted. Quote or paraphrase them wherever a figure could be misread. If a
document says `stale: true`, say so next to the number.

Do not recompute what a section, chart document, or metric tile already
states. Simple derivations (a row count, the difference between two buckets)
are fine, but say you derived it and from which document.

Time series:

- A bucket marked `partial` (the current year or month) is never compared with
  a complete one.
- Use the document's `comparison` pair when present; otherwise compare the
  last two complete buckets and name them.
- Heatmaps show the top 25 only. They show who carries the work, not totals.
- There is no 180-day period. Periods are `7d`, `30d`, `365d` and all-time. For
  a mid-year view use the monthly buckets, excluding the partial month.

## 5. Write the draft

Follow the template in `references/report-structure.md`. Rules:

1. **Every number carries its source:** the section, chart or metric id, plus
   the data-as-of date. Put the JSON URL where a reader can follow it, and name
   the dashboard tab and chart. A short `Source:` line under each block beats
   inline clutter. Charts are drawn from JSON, so there are no image URLs.
2. **Never write a judgment section yourself.** Progress against goals, next
   goals, help required, the community-calls narrative and the lifecycle
   recommendation are `> [MAINTAINER INPUT]` slots. State the question the
   TAC asks, and list the evidence in the draft that bears on it. Pointing at
   evidence is fine; drawing the recommendation is not.
3. **Describe, don't editorialise.** "The committer bench spans N employers" is
   a finding. "Diversity is healthy" is a judgment: attribute it to the TAC
   criterion or leave it to the slot.
4. **Print coverage caveats next to the figures they limit.** Affiliation known
   share, HIP absence-of-evidence, manual Discord exports and the like.
5. **When two documents disagree about the same thing, report both** with their
   ids. Do not pick one silently.
6. Plain prose and tables, in the style of Hiero's earlier reports. No emoji,
   no hype.

## 6. Data Gaps appendix

Every report ends with the appendix described in `references/gap-appendix.md`.
It is a first-class deliverable, not an apology. Each entry names what the TAC
wants, why the API cannot answer it, the closest signal available, and the
follow-up that would close the gap. An empty appendix almost certainly means
the checks were skipped.

## 7. Repo-specific traps

- **"Adoption" means two different things.** The TAC's "adoption" is who uses
  the project (ADOPTERS.md). The HIPs "adoption funnel" is how far improvement
  proposals get implemented. Never use the funnel as evidence of adopters.
- **Unknown is not independent.** "Unknown" means no public signal could place
  the person; "independent" means no named employer. Report the affiliation
  known share (a metric tile) whenever you quote an organisation chart.
- **Role tabs are disjoint.** Each person counts once, at their highest role
  anywhere, so maintainer and committer figures can be added or compared.
- **Counts are GitHub logins, bots excluded.** They are not people, and they
  will not match other tools' "authors" counts (e.g. LFX Insights). Never
  merge numbers from the two sources.
- **Only some activity is tracked:** PRs, issues, reviews, merges and label
  changes. Comments and reactions are not, so activity is not discussion.
- **HIP evidence is evidence, not completion.** "No reference found" is absence
  of evidence. Only the Hiero era (since September 2024) is counted.
- **Release staleness ranking** is dominated by repos that never ship a GitHub
  Release (docs, governance, meta). Do not call them neglected.
- **Discord is a manual export**, published once under hiero-ledger, and
  silently ages. If it is absent or its date is old, it is a gap.
- **Chart PNGs were retired in October 2026.** Older docs and issues that list
  "PNG-only" data as a gap are out of date: check the chart documents first,
  because the data is probably there as JSON.
- **The API is `v1`, additive-only, and flagged `wip`.** Say so in the
  provenance block.

## 8. Before handing it back

- Trace three numbers back to their JSON documents and confirm them.
- Count the `[MAINTAINER INPUT]` slots and list them at the end of your reply,
  so the maintainer knows exactly what is theirs to write.
- Run `git status`: no tracked file may have changed. Save the draft under
  `outputs/lfdt-report/` (generated output is not committed; check with
  `git check-ignore`) or wherever the maintainer asks.
- Report which manifest the draft ran against (`generated_at`, `git_sha`).
- Do not commit, push, or open a PR. Maintainers file the report with LFDT,
  which means adding it under `tac/project-updates/<year>/` and updating the
  `mkdocs.yml` nav, as the TAC instructions describe.
