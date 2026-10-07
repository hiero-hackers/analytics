# The Data Gaps appendix

The appendix has three parts, always in this order.

## 1. Provenance

```
API version: v1 (work in progress: <wip value>)
Manifest generated: <generated_at>
Analytics revision: <provenance.git_sha>
Data as of (oldest dataset watermark): <provenance.data_as_of>
TAC instructions read: <date, and "matched snapshot" or what differed>
Stale documents cited: <ids, or none>
```

## 2. Gaps

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

For missing macros, quote `macro_absent_notes[macro]` verbatim and add
nothing to it.

**A gap is only a gap after checking.** Search the manifest's sections, chart
documents and metric tiles before declaring one. Chart documents especially:
data once published only as PNGs is now JSON, so the older gap lists may be
out of date.

### Expected gaps to verify each run

These are things the TAC asks for, or that Hiero's own earlier reports cited,
that were not in the `hiero-ledger` manifest on 2026-10-06. They are
expectations to check, not facts to copy:

- **Adopters:** the ADOPTERS file, how many organisations use the project and
  how that changed. (The HIP funnel is not a substitute.)
- **Community calls:** cadence, attendance, new call series.
- **Discord:** the Community macro was absent from the hiero-ledger manifest,
  and even when present it counts messages, not response times.
- **Issue and PR resolution speed:** time to first response, time to close or
  merge. `issue-difficulty` describes the open queue only.
- **CI health:** job failure rate and queue time, which Hiero's 2026 annual
  report cited from GitHub Actions metrics. Only runner types are published.
- **TSC review counts:** how many improvement proposals the TSC reviewed in
  the period. The HIPs macro reports spec status and implementation evidence,
  not dated review events; check `hip-board` before declaring it a gap.
- **Since-last-report deltas:** the API publishes the current state plus
  time series, not the previous report's figures. Deltas are possible only
  where a time series covers the interval, or where the maintainer supplies
  the prior numbers. Check `docs/snapshots.md` for what history exists.
- **File hygiene checks:** whether MAINTAINERS and ADOPTERS files and the
  roadmap are current and public. The affiliation pipeline reads MAINTAINERS
  files but does not validate them.
- **Governance requirement checklist:** whether the project met every TAC
  governing-document requirement. Not measurable from GitHub activity.
- **Contributor counts from other tools** (for example LFX Insights authors):
  different definitions, never mix.

## 3. Coverage checklist

Close with one line per TAC question, so a reviewer sees at a glance what is
done:

```
Q1 Progress against goals     : maintainer input
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
