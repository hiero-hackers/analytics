# The hand-back note

What the maintainer reads when the draft is done. Same order every time, so
they can skim it. Nothing in it repeats the draft.

```
Draft status: data to 6 October 2026; re-run after 31 December 2026 before filing.
                                   (or: complete period, ready to fill in)

Files
- <path>/2027-annual-Hiero.md          the draft (what gets filed)
- <path>/figures/*.svg, *.png          3 figures; PNGs are what GitHub attachments take
- <path>/2027-annual-Hiero.pdf         review copy for the TSC, not for filing

Ran against manifest generated 2026-10-06T09:15Z, analytics revision 62a5652.
check_draft.py: passed (or: N warnings, listed below)

Yours to write (9 slots)
1. Community Calls
2. Project composition
3. Improvement Proposals Adopted: TSC review count
4. Maintainer Diversity: what is being done
5. Project Adoption
6. Performance Against Prior Goals: the Result column, 8 rows
7. 2027 Year's Goals
8. Help Required
9. Lifecycle recommendation (current stage per the 2026 review: Graduated)

To file
1. Fill the slots; delete the "> [MAINTAINER INPUT]" lines.
2. Upload figures/*.png to the governance PR (drag into the description),
   replace each ![...](figures/...) line with the <img> GitHub inserts.
3. Add the file under tac/project-updates/2027/ and the mkdocs.yml nav
   entry under 2027 → 1H. Open the PR against lf-decentralized-trust/governance.

Data defects seen this run (candidates for analytics issues; see the
Data notes appendix for ids)
- <one line each>
Hand this list to /write-analytics-issue to turn into issues.

Numbers traced: <tile>, <table row>, <chart bucket>: all matched.
```

Rules:

- The re-run warning is the first line whenever the period is incomplete.
- Paths are absolute. Say once that the files are untracked.
- The slot list matches the draft exactly; count them with `check_draft.py`.
- Never paste the draft, a figure, or the gap list into the note.
