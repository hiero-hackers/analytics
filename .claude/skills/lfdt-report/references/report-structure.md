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
- Add the file to `mkdocs.yml` nav under the year's group for the report
  type. The live 2026 nav uses "Annual" and "MidYear"; the instruction
  page's "1H"/"2H" wording is older. Check the live `mkdocs.yml`.

## Template

Hiero's 2026 annual review uses the headings marked (Hiero 2026). Reuse them
exactly so reviewers see the shape they already know. Two headings marked
(added) are not in that review; they hold data the TAC asks for that the 2026
review carried in prose. Drop them if the maintainer prefers the original
shape and fold their content into "GH Organization Overview".

For an org without the Governance and HIPs macros, keep the headings, make
"Maintainer Diversity" and "Improvement Proposals Adopted" a one-line gap
pointer each, and put the activity fallbacks (repository growth, contributor
period counts, heatmap months) under "GH Organization Overview". Say in the
header that the draft is not for filing.

Slots are written exactly like this, with a bare `>` line between the
question and the evidence so Markdown does not run them together:

```
> [MAINTAINER INPUT] <the question the TAC asks, in one line>
>
> Evidence in this draft: <section names and figure numbers that bear on it, or "none">
```

Every slot has both lines, including Help Required and the goals slots.

```markdown
[//]: # (SPDX-License-Identifier: CC-BY-4.0)

# {YEAR} Annual Review Hiero          (mid-year: "# {YEAR} Mid-Year Review Hiero")

*Data as of {6 October 2026} from the [Hiero analytics dashboard](https://hiero-hackers.github.io/analytics/);
period covered {January to December 2026}; provenance and data notes in the appendix.*

## Project Health                                                   (Hiero 2026)
Two or three paragraphs: repositories, people active, the activity trend,
with inline links and source numbers. The TAC's "consistent or increasing
contribution activity" is answered here. Figures go directly under the
paragraph they illustrate, wherever that falls; the figure numbers below
are the default order.

### GH Organization Overview                                        (Hiero 2026)
Roles held versus roles active (approximately: tiles count current roles,
the yearly series the role held at the time); the understaffed and
quiet-holder findings in one paragraph; the onboarding queue described
without a count, because the two published views disagree. One short
table. Figure 1: active contributors by role per year. Figure 2: repository
count.

### Deliverables                                                    (added)
Releases in the period (derived, said once) and cadence. Annual question 2
/ mid-year question 2. HIPs are covered once, under Improvement Proposals.

### Community Calls                                                 (Hiero 2026)
> [MAINTAINER INPUT] Cadence, attendance, new call series.
> Evidence in this draft: none (Discord data only if the Community macro is present).

### Project composition                                             (Hiero 2026)
> [MAINTAINER INPUT] Projects adopted or proposed this period
> (hiero-ledger/tsc issues labelled "project proposal").
> Evidence in this draft: repository growth (Figure 2).

### Improvement Proposals Adopted                                   (Hiero 2026)
One paragraph, at most four numbers: specs in the inventory, approved, with
merged implementation evidence, and the Hiero-era cohort. Detail rows and
the funnel-versus-table difference go to the appendices.
> [MAINTAINER INPUT] How many proposals the TSC reviewed and approved this
> period (the 2026 review cited 15 from the TSC project board).
> Evidence in this draft: the HIP paragraph above; TSC activity by repository (appendix).

### Security and Supply-Chain Posture                               (added)
One paragraph: Scorecard range and the published median, CODEOWNERS
coverage, runner mix. Declared configuration, not enforcement, said once.

## Maintainer Diversity                                             (Hiero 2026)
Two paragraphs: employer shares with the known-share caveat in the first
sentence; concentration (single-employer repositories and teams: the
dashboard's count is the headline, the table's wider reading is a data
note, since they measure different things); the active-maintainer trend. One short
table of the top employers for both roles. Figure 3: maintainers by employer.
> [MAINTAINER INPUT] What is being done about it.
> Evidence in this draft: Maintainer Diversity, Figures 1 and 3.

## Project Adoption                                                 (Hiero 2026)
> [MAINTAINER INPUT] Adopters and how they changed (ADOPTERS.md; the 2026
> review cited 50+ companies). The API has no adopter data.
> Evidence in this draft: none.

## Goals                                                            (Hiero 2026)

### Performance Against Prior Goals                                 (Hiero 2026)
> [MAINTAINER INPUT] Progress against last year's goals, including the challenges met.
>
> Evidence in this draft: the Evidence column of the table below.

| Goal (from the {YEAR-1} review) | Purpose, in a line | {YEAR-1} result | Evidence in this draft |
|---|---|---|---|
| 1. ... | ... | [MAINTAINER INPUT] | Figure 1; Maintainer Diversity |
| 2. ... | ... | [MAINTAINER INPUT] | none |

(The prior table, verbatim, is in Appendix: Supporting tables.)

### {YEAR} Year's Goals            (mid-year: "### Goals for the second half")   (Hiero 2026)
> [MAINTAINER INPUT] Goals and stretch goals, how they will be achieved, where the public roadmap lives.
>
> Evidence in this draft: none; the gaps appendix lists what the data cannot yet show.

### Help Required                                                   (Hiero 2026)
> [MAINTAINER INPUT] Whether the project needs help from the TAC or LFDT, and with what.
>
> Evidence in this draft: understaffed repositories and quiet role holders (GH Organization Overview).

## Project Lifecycle Status Recommendation                          (Hiero 2026)
> [MAINTAINER INPUT] Current stage per the {YEAR-1} review: {Graduated}. The recommendation is the maintainers' to make.
> Evidence in this draft: Figures 1 to 3, Deliverables, Security.

## Appendix: Supporting tables
Every table the body summarises, each with a `Source:` line: releases by
repository, HIP detail rows, the full employer breakdown, the Scorecard
list, TSC activity by repository, the prior goals table verbatim.

## Appendix: Sources
Numbered list, one entry per distinct document cited:
`[3] Chart maintainer-pipeline, All time variant (maintainer_pipeline_yearly), data as of 2026-10-06. JSON: BASE/hiero-ledger/charts/maintainer_pipeline_yearly.json. Dashboard: <deep link>.`
Define BASE once at the top of this appendix.

## Appendix: Data notes and gaps
(see gap-appendix.md: provenance, data notes, gaps, coverage checklist)
```

## Mid-year template

The mid-year review is a different document, not a shorter annual. The one
2026 mid-year review filed so far (AnonCreds) is about 700 words, eight flat
`##` sections, no tables, no images, 25 links; the 2026 annuals range from
about 700 (Besu) to 2,500 words (Hiero). Hiero has not filed a mid-year yet,
so match the mid-year shape, keep Hiero's register, and aim for 900 to
1,200 words of body with one figure at most.

Period: January to June (the schedule page sets the due date, usually late
August or September; name the months). Every data statement is "in the six
months" or "at <date>"; derive the six-month figures with `derive.py months`
and `derive.py releases` and say so once in the appendix. The monthly
active-by-role series holds twelve months, so "the six months before" is
usually only partly available: compare with the months that exist and say
which. Heatmaps cover the last six complete months at the data date, not
the period, unless the draft is run in July.

```markdown
[//]: # (SPDX-License-Identifier: CC-BY-4.0)

# {YEAR} Mid-Year Review Hiero

*Data as of {date} from the [Hiero analytics dashboard](https://hiero-hackers.github.io/analytics/);
period covered {January to June YEAR}; provenance and data notes in the appendix.*

## Project Health
Two paragraphs: people active per month over the six months against the
months before that the series holds (range, not a sum), releases in the
period, repositories added. The TAC's mid-year criteria "consistent or
increasing activity" and "deliverables being produced" are answered here.
One figure at most: active contributors by role, monthly, twelve months.
> [MAINTAINER INPUT] Community calls, Discord responsiveness and GitHub
> PR and issue responsiveness in the period (the TAC asks whether questions
> are answered and PRs and issues resolved promptly; the API has no
> response-time data).
>
> Evidence in this draft: none.

## Maintainer Diversity
One paragraph: employer shares now, with the known-share caveat; what moved
since the annual, from the monthly active-by-role series and, if the
maintainer supplies them, the annual's figures. Question 5: changes.
> [MAINTAINER INPUT] What changed and why; what is being done.
> Evidence in this draft: Maintainer Diversity above.

## Project Adoption
> [MAINTAINER INPUT] Adopters added or lost since the annual (ADOPTERS.md).
> Evidence in this draft: none; the API has no adopter data.

## Performance Against Prior Goals
> [MAINTAINER INPUT] Progress against this year's goals, as set in the annual.

| Goal (from the {YEAR} annual) | Purpose, in a line | Progress at mid-year | Evidence in this draft |
|---|---|---|---|
| 1. ... | ... | [MAINTAINER INPUT] | ... |

### Achievements
> [MAINTAINER INPUT]

### Outstanding Tasks
> [MAINTAINER INPUT]

## Goals for the second half
> [MAINTAINER INPUT] Including any goals revised since the annual (the TAC
> instructions invite that).

## Help Required
> [MAINTAINER INPUT]
> Evidence in this draft: understaffed repositories and quiet role holders, if notable in the period.

## Project Lifecycle Stage Recommendation
> [MAINTAINER INPUT] Current stage per the {YEAR} annual: {Graduated}.

## Appendix: Supporting tables
(the prior goals table as filed; otherwise only what a body statement needs)
## Appendix: Sources
## Appendix: Data notes and gaps
```

The mid-year has no Deliverables, Security or HIP sections; releases and
the HIP headline belong in the Project Health paragraphs, and Scorecard
posture is mentioned only if it changed. The mid-year criteria the annual
lacks (Discord and GitHub responsiveness) are both gaps today; say so in
the slot and the appendix rather than padding the body.

Body sections carry no `Source:` lines; the bracketed numbers do that work.
A `Source:` line under an appendix table looks like:

```
Source: section understaffed, 365d period table (4 rows; 16 all time); data as of 2026-10-06.
JSON: BASE/hiero-ledger/understaffed.json
```
