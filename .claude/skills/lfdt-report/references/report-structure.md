# TAC report structure

Snapshot verified October 2026 against the live instructions (paraphrased; the
live pages are authoritative and the skill re-reads them every run):

- Annual: <https://lf-decentralized-trust.github.io/governance/project-updates/annual-review-instructions/>
- Mid-year: <https://lf-decentralized-trust.github.io/governance/project-updates/mid-year-update-instructions/>
- Models to match in tone and structure (fetch the raw markdown from
  `https://raw.githubusercontent.com/lf-decentralized-trust/governance/main/tac/project-updates/<year>/<file>.md`):
  - Hiero's 2026 annual review: `2026/2026-annual-Hiero.md`
  - A 2026 mid-year review: `2026/2026-MidYear-AnonCreds.md`

## What each report must answer

**Annual** (a "big picture" assessment, filed at the start of the year):

1. How did the project progress against last year's goals?
2. What deliverables or outputs did it have in the past year?
3. What are the goals for this year?
4. Does the project need any help?
5. What is the maintainer and contributor diversity?

**Mid-year** (the six months since the annual review; all projects file two
reports a year from 2026):

1. How is the project progressing against its yearly goals?
2. What deliverables or outputs did it have in the past six months?
3. What are the goals for the second half of the year?
4. Does the project need any help?
5. What changed in maintainer and contributor diversity?

## What the TAC evaluates

Both reports: whether the governance-document requirements were met; signs of
consistent or increasing contribution activity; maintainer diversity by
organisation, and whether the number of active maintainers rose or fell over the
past year (the MAINTAINERS file should be current); adoption and how it has
changed (the ADOPTERS file should be current); performance against goals,
including the challenges met; and the goals and stretch goals ahead (the
roadmap should be current and public).

Mid-year adds: whether Discord questions are answered promptly; whether GitHub
PRs and issues are resolved promptly; and whether deliverables (releases,
standards updates) are being produced.

Afterwards the responsible TAC reviewers add their evaluation and
recommendations to the PR, and follow-ups become issues in the governance repo.
None of that is this skill's job.

## Filing details the maintainer needs

- File name: `YYYY-annual-Hiero.md` or `YYYY-MidYear-Hiero.md` under
  `tac/project-updates/<year>/` (the 2026 directory uses both spellings of
  "annual"; keep Hiero's lower-case one).
- First line: `[//]: # (SPDX-License-Identifier: CC-BY-4.0)`.
- Add the file to `mkdocs.yml` nav under the year and "1H" (annual) or "2H"
  (mid-year).

## Template

For an org without the Governance and HIPs macros, keep the headings, make
"Maintainer Diversity" and "Improvement Proposals Adopted" a one-line gap
pointer each (quoting the absent note), and put the activity fallbacks
(`repo-growth`, `profiles` periods, heatmap months) under "GH Organization
Overview". Say in the header that the draft is not for filing.

Hiero's 2026 annual review uses the headings marked (Hiero 2026). Reuse them
exactly so reviewers see the shape they already know. Two headings marked
(added) are not in that review; they hold data the TAC asks for that the 2026
review carried in prose. Drop them if the maintainer prefers the original
shape and fold their content into "GH Organization Overview".

Slots are written exactly like this:

```
> [MAINTAINER INPUT] <the question the TAC asks, in one line>
> Evidence in this draft: <section names / ids that bear on it>
```

```markdown
[//]: # (SPDX-License-Identifier: CC-BY-4.0)

# {YEAR} Annual Review Hiero          (mid-year: "# {YEAR} Mid-Year Review Hiero")

Data as of {data_as_of} · API generated {generated_at} · analytics revision {git_sha}
Period covered: {period, as months}. Source: {BASE}/manifest.json (API v1, work in progress).

## Project Health                                                   (Hiero 2026)
One or two paragraphs: what the period looked like in numbers. Open with the
headline figures (repos, contributors, active-maintainer trend) and their
sources; leave the narrative tone to the maintainer.

### GH Organization Overview                                        (Hiero 2026)
(data) Repository count, contributor base, and activity trend. Questions:
"consistent or increasing contribution activity".

### Deliverables                                                    (added)
(data) Releases (cadence, staleness, repos that shipped) and HIP implementation
evidence. Annual question 2 / mid-year question 2.

### Community Calls                                                 (Hiero 2026)
> [MAINTAINER INPUT] (and Discord data only if the Community macro is present)

### Project composition                                             (Hiero 2026)
> [MAINTAINER INPUT] Projects adopted or proposed this period
> (hiero-ledger/tsc issues labelled "project proposal").

### Improvement Proposals Adopted                                   (Hiero 2026)
(data) Spec status and implementation evidence from the HIPs macro, headline
figures only; detail rows go to the supporting-tables appendix.
> [MAINTAINER INPUT] How many proposals the TSC reviewed and approved this
> period (the 2026 review cited 15 from the TSC project board). The API has
> no dated review events; `tscrepo` is the closest activity signal.

### Security and Supply-Chain Posture                               (added)
(data) OpenSSF scorecard, CODEOWNERS coverage, CI runners.

## Maintainer Diversity                                             (Hiero 2026)
(data) Roles, employer diversity, concentration, and the active-maintainer
trend, with the affiliation known-share tiles beside every employer figure.
Annual question 5 / mid-year question 5.
> [MAINTAINER INPUT] What is being done about it.

## Project Adoption                                                 (Hiero 2026)
> [MAINTAINER INPUT] Adopters and how they changed. The API has no adopter data
> (see the Data Gaps appendix).

## Goals                                                            (Hiero 2026)

### Performance Against Prior Goals                                 (Hiero 2026)
> [MAINTAINER INPUT] (annual: last year's goals; mid-year: this year's goals so far)
> Prior goals, copied verbatim from the "{YEAR-1} Year's Goals" table of {prior report URL}:
> <the goals table or list, verbatim>
> Evidence in this draft: <ids>

### {YEAR} Year's Goals            (mid-year: "### Goals for the second half")   (Hiero 2026)
> [MAINTAINER INPUT]

### Help Required                                                   (Hiero 2026)
> [MAINTAINER INPUT]

## Project Lifecycle Status Recommendation                          (Hiero 2026)
> [MAINTAINER INPUT] The recommendation is the maintainers' to make.
> Evidence in this draft: <ids>

## Appendix: Supporting tables
Per-repo releases, HIP evidence, employer breakdowns and any other table the
body summarises. Each with its own `Source:` line.

## Appendix: Data Gaps and Provenance
(see gap-appendix.md)
```

Not every data block needs prose, but every section needs at least one
sentence saying what the table shows. A short table plus a `Source:` line is
the clearest form for the numbers themselves.

A `Source:` line looks like:

```
Source: Governance tile "maintainers" (104) and chart `maintainer-pipeline`,
All time variant, buckets 2024 and 2025 (2026 partial, excluded); data as of
2026-10-06. JSON: {BASE}/hiero-ledger/charts/... · Dashboard:
https://hiero-hackers.github.io/analytics/#tab=Governance&org=hiero-ledger&widget=maintainer-pipeline
```
