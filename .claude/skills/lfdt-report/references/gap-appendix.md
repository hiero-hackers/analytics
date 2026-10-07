# Appendix: Data notes and gaps

The last appendix has four parts, always in this order. It is where every
identifier, field name and method remark that the body is not allowed to
carry ends up.

## 1. Provenance

```
BASE: https://hiero-hackers.github.io/analytics/data/api/v1 (manifest at BASE/manifest.json)
Draft status: <"complete period" or "data to <date>; re-run after <period end> before filing">
API version: v1 (work in progress: <wip value>)
Manifest generated: <generated_at>
Analytics revision: <provenance.git_sha>
Data as of (oldest dataset watermark): <provenance.data_as_of>
TAC instructions read: <date, and "matched snapshot" or what differed>
Prior report read: <URL, or "not available: <reason>">
Stale documents cited: <ids, or none>
Partial buckets excluded: <ids and bucket names, or none>
```

## 2. Data notes

One bullet per thing a careful reader would otherwise trip on, with ids:

- Both sides of every disagreement the body mentions qualitatively (the
  two open-issue views, the two single-employer counts, funnel versus
  evidence table, the two repository counts), with a one-line reason.
- Counting rules that matter: GitHub accounts not people; highest-role
  counting and where it does and does not allow sums; the bot name rule
  and any automation accounts seen in the tables.
- Every `Derived:` line from `derive.py`, and any derivation done by hand
  (what was computed, from which documents).
- Data defects noticed this run (stale absent-macro notes, unnormalised
  employer names, methodology text wrong about its document). These are
  the seeds of analytics issues; keep them terse and factual.

## 3. Gaps

One entry per item the TAC asks for that the API could not supply. Use this
shape, short and concrete:

```
### <What the TAC wants, in a few words>
- Needed for: <annual Q2 / mid-year Q5 / evaluation criterion ...>
- Why the API cannot answer: <not collected / collected but not published /
  org has no config / no rows / stale / only partial coverage>
- Closest available signal: <section or chart id, with its caveat, or "none">
- To close it: <the smallest follow-up: a new section, a new pipeline output,
  or a manual maintainer input>
```

For missing macros, quote `macro_absent_notes[macro]` verbatim, then add
one sentence stating this org's actual state (the notes are global and can
contradict the org's own manifest).

**A gap is only a gap after checking.** Search the manifest's sections, chart
documents and metric tiles before declaring one. Chart documents especially:
data once published only as PNGs is now JSON, so the older gap lists may be
out of date. And a finding-type section with zero rows (no gone-dark
holders, no understaffed repos) is a result, not a gap; see SKILL.md step 3.

### Expected gaps to verify each run

These are things the TAC asks for, or that Hiero's own earlier reports cited,
that were not in the `hiero-ledger` manifest on 2026-10-06. They are
expectations to check, not facts to copy:

- **Adopters:** the ADOPTERS file, how many organisations use the project and
  how that changed. (The HIP funnel is not a substitute.)
- **Community calls:** cadence, attendance, new call series.
- **Projects adopted or proposed:** the API publishes repository counts per
  month but not the new repositories' names or creation dates, and does not
  collect the "project proposal" issues in hiero-ledger/tsc.
- **Discord:** the Community macro was absent from the hiero-ledger manifest,
  and even when present it counts messages, not response times.
- **Issue and PR resolution speed:** time to first response, time to close or
  merge. `issue-difficulty` describes the open queue only.
- **CI health:** job failure rate and queue time, which Hiero's 2026 annual
  report cited from GitHub Actions metrics. Only runner types are published
  (`ownership` card, Runners variant).
- **TSC review counts:** how many improvement proposals the TSC reviewed in
  the period. The HIPs macro reports spec status and implementation evidence,
  not dated review events. Check `hip-board` and cite the Governance section
  `tscrepo` (TSC activity by repo) as the closest signal before declaring it
  a gap.
- **Since-last-report deltas:** the API publishes the current state plus
  time series, not the previous report's figures. Deltas are possible only
  where a time series covers the interval (the monthly `maintainer-pipeline`
  buckets do), or where the maintainer supplies the prior numbers. The
  snapshot archive (`docs/snapshots.md`) is the orphan branch
  `data/snapshots` of hiero-hackers/analytics; `git fetch origin
  data/snapshots` and read `api/v1/` at an older commit for a dated tile
  value. History starts 2026-08-07, so it gives short deltas, not a
  prior-year baseline, until it has run for a year.
- **File hygiene checks:** whether MAINTAINERS and ADOPTERS files and the
  roadmap are current and public. The affiliation pipeline reads MAINTAINERS
  files but does not validate them.
- **Governance requirement checklist:** whether the project met every TAC
  governing-document requirement. Not measurable from GitHub activity.
- **Contributor counts from other tools** (for example LFX Insights authors):
  different definitions, never mix.

## 4. Coverage checklist

Close with one line per TAC question, so a reviewer sees at a glance what is
done:

```
Q1 Progress against goals     : maintainer input (prior goals pre-filled)
Q2 Deliverables               : data (Releases, HIPs) + gaps (...)
Q3 Goals                      : maintainer input
Q4 Help                       : maintainer input
Q5 Diversity                  : data (Governance), known share 99% / 77%
Evaluation: activity trend    : data (...)
Evaluation: active maintainers: data (maintainer-pipeline)
Evaluation: adoption          : gap
Evaluation: roadmap           : maintainer input
```

(The percentages are an example; copy the live ones from the metric tiles.)

Gaps that repeat across runs are the real output: collect them into follow-up
issues. They are deliberately out of scope for the skill itself.
