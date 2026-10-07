# TAC report structure

Snapshot verified October 2026 against the live instructions (paraphrased; the
live pages are authoritative and the skill re-reads them every run):

- Annual: <https://lf-decentralized-trust.github.io/governance/project-updates/annual-review-instructions/>
- Mid-year: <https://lf-decentralized-trust.github.io/governance/project-updates/mid-year-update-instructions/>
- A real model to match in tone and structure:
  <https://lf-decentralized-trust.github.io/governance/project-updates/2026/2026-annual-Hiero/>

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

## Template

Hiero's 2026 annual review uses these headings. Reuse them so reviewers see
the shape they already know. File name for the maintainers who file it:
`YYYY-annual-Hiero.md` or `YYYY-MidYear-Hiero.md`.

Slots are written exactly like this:

```
> [MAINTAINER INPUT] <the question the TAC asks, in one line>
> Evidence in this draft: <section names / ids that bear on it>
```

```markdown
# {YEAR} Annual Review {Project}        (mid-year: "# {YEAR} Mid-Year Review {Project}")

Data as of {data_as_of} · API generated {generated_at} · analytics revision {git_sha}
Period covered: {period}. Source: {BASE}/manifest.json (API v1, work in progress).

## Project Health

### GH Organization Overview
(data) Repository count, contributor base, and activity trend. Questions:
"consistent or increasing contribution activity".

### Deliverables
(data) Releases (cadence, staleness, repos that shipped) and HIP implementation
evidence. Annual question 2 / mid-year question 2.

### Community Calls
> [MAINTAINER INPUT] (and Discord data only if the Community macro is present)

### Project Composition
> [MAINTAINER INPUT] Projects adopted or proposed this period.

### Improvement Proposals
(data + slot) Spec status and implementation evidence from the HIPs macro; the
count of proposals the TSC reviewed this period is a slot unless the API
supplies it.

### Security and Supply-Chain Posture
(data) OpenSSF scorecard, CODEOWNERS coverage, CI runners.

## Maintainer Diversity
(data) Roles, employer diversity, concentration, and the active-maintainer
trend. Annual question 5 / mid-year question 5.
> [MAINTAINER INPUT] What is being done about it.

## Project Adoption
> [MAINTAINER INPUT] Adopters and how they changed. The API has no adopter data
> (see the Data Gaps appendix).

## Goals

### Performance Against Prior Goals
> [MAINTAINER INPUT] (annual: last year's goals; mid-year: this year's goals so far)

### {YEAR} Goals          (mid-year: "Goals for the second half")
> [MAINTAINER INPUT]

### Help Required
> [MAINTAINER INPUT]

## Project Lifecycle Status Recommendation
> [MAINTAINER INPUT] The recommendation is the maintainers' to make.

## Appendix: Data Gaps and Provenance
(see gap-appendix.md)
```

Not every data block needs prose. A short table plus a `Source:` line is often
the clearest form.
