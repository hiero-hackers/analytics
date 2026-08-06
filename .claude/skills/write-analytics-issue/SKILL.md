---
name: write-analytics-issue
description: Draft a GitHub issue for this repo at the right contributor level (Good First Issue, Beginner, Intermediate, or Advanced), following the .github/ISSUE_TEMPLATE house style. Use whenever asked to write, draft, seed, or refresh issues for this repository.
---

# Writing issues for this repo

Issues here are the contributor funnel. A vague one wastes a newcomer's evening;
a wrong one wastes their goodwill. The bar is that someone who has never seen
this codebase can start work from the issue alone.

## 1. Verify the gap is real — before anything else

**Most rejected drafts describe problems that were already solved.** Read the
code first, every time. Real examples from seeding this repo:

- "add alt text to chart images" — `alt={chart.title}` was already there; the
  actual gap was that alt text didn't vary between chart variants.
- "make the lightbox close on Escape" — Escape already worked; focus trapping
  did not.
- "default-sort CODEOWNERS by missing-first" — already sorted, and already
  covered by a test.

So: `grep` for the thing before claiming it's absent, and read the surrounding
module rather than the one function. If the gap turns out to be narrower than
the request, **file the narrower issue** and say what already exists — that is
more useful than the original idea.

Then check nobody has filed it: `gh issue list --repo hiero-hackers/analytics --state open`.
Check open PRs too; a fix may be in flight.

## 2. Pick the level honestly

From `CONTRIBUTING.md#skill-levels` — the testing bar is part of the level, not
an afterthought:

| Level | Time | Testing bar | The issue should… |
|---|---|---|---|
| **Good First Issue** | ~4 h incl. setup | run it, check the happy path | prescribe the approach, file by file |
| **Beginner** | ~8 h | basic unit tests for the change | name the files and one similar pattern to study; leave the implementation open |
| **Intermediate** | ~25 h | happy path + edge cases + errors | state outcome and constraints only; the contributor comments their approach before coding |
| **Advanced** | ~30 h+ | comprehensive | state the problem and the forces on it; expect a design/impact note in the PR |

Signals you have the level wrong: a "Good First Issue" that needs a design
decision; an "Advanced" whose answer is obvious once you read one file.

## 3. Draft from the template

Start from the matching file in `.github/ISSUE_TEMPLATE/` (`01-good-first-issue.md`
… `04-advanced-issue.md`). **Everything outside "The task" is boilerplate: keep
it verbatim.** It carries the CONTRIBUTING links (setup, workflow, AI policy,
testing, getting help) that make the issue self-contained — never paraphrase or
trim those.

Do adapt the checklist's test commands to what the change actually touches:

- Python only → `uv run pytest` and `uv run ruff check src tests`
- Frontend only → `npm test`, `npm run lint`, `npm run build` in `web/`
- Both → both

Write "The task" as three parts:

- **Problem** — what is wrong or missing, observable today, and why it matters.
  Cite `file.py:LINE` for the specific claim. Write for someone who has never
  seen this codebase.
- **What done looks like** — measurable, naming the test suites that must pass.
  Where a design decision exists, either make it (lower levels) or name it as
  the contributor's to make (higher levels). Never leave it silently open: an
  unmade decision is what stalls an issue for months.
- **Where to start** (GFI/Beginner) or **Modules involved / constraints**
  (Intermediate/Advanced) — 1–3 real paths you verified, each with a phrase
  about what the reader will find there. **Never guess a path, line number, or
  symbol name.**

Title: imperative and specific, no prefix tag. "Add a 180-day window to the
difficulty-by-repo tabs", not "fix: difficulty windows".

## 4. Repo-specific traps to write into the issue

If the change touches these, say so in the issue — contributors hit them blind
otherwise, and reviewers will send the PR back:

- **The output contract.** `tests/contracts/test_output_contract.py` pins every
  CSV and PNG the pipelines produce. A new or renamed output fails the build
  until it is declared. Tell the contributor this is a deliberate contract
  update, not a test to work around.
- **Charts must self-explain.** Spec tests require every chart to carry both a
  `CHART_NOTES` entry and a `CHART_METHODOLOGY` list in its `dashboard_spec/`
  family. An issue adding a chart must ask for both.
- **Column formats are a closed set.** `dashboard_spec.COLUMN_FORMATS` is the
  single source; the frontend's `FormattedCell` implements exactly those.
- **Run shapes.** Anything touching pipelines or the dataset store must survive
  a single-pipeline CLI run, an offline run, and extra orgs — not just the full
  scheduled run. This is the most common source of "worked locally, wrong in CI".
- **Two-layer staleness.** The TTL cache and the durable dataset store have
  deliberately different semantics; read the module docstrings before proposing
  changes to fetch paths.

## 5. Evidence beats description

- **Reproduce the bug** on the live dashboard (<https://hiero-hackers.github.io/analytics/>)
  and write the exact steps and observed result into the issue. A verified repro
  is worth more than a paragraph of theory, and it sometimes reveals a second
  symptom worth naming.
- **Embed a live chart PNG** with a plain markdown image link when the chart
  *is* the evidence — those URLs are public and stable.
- Screenshots must be drag-dropped by a human; the GitHub API cannot upload
  issue attachments. Say so rather than promising an image you cannot add.
- Quantify claims you make. "The payload is large" is weak; "profiles.json is
  1.0 MB, of which the `all` period duplicates the base rows" is actionable.

## 6. Labels

Apply, in this order:

- **Level:** `good first issue` / `beginner` / `intermediate` / `advanced`
- **Kind:** `bug` or `enhancement` (`documentation` for docs-only)
- **Language:** `python` and/or `typescript`, so contributors can self-select.
  Both, for changes that cross the Python↔React contract.
- **`CI/CD`** when the work is mostly workflow files — CONTRIBUTING treats
  demonstrated CI/CD proficiency as a substitute prerequisite.
- **`tests`** when the deliverable is test infrastructure.

**Do not apply `analytics`.** The whole repository is analytics; the label
carries no information. (It still exists on older issues.)

## 7. Superseding a stale issue

When an issue's file pointers have gone stale but the problem is real, do not
silently rewrite it. Close it as *not planned* with a comment naming the
replacement, and open a fresh one that:

- opens with `*Supersedes #N (closed as stale — reason).*`
- **preserves the original research verbatim** and credits its author by handle
- updates every path against the current tree
- resolves any question the original left open

Losing a contributor's research to a tidy-up is worse than a stale link.

## 8. Before creating anything

**Show the maintainer the list of candidate issues — titles, levels, and a
one-line problem each — and get approval before creating any of them.** Bulk-
creating unreviewed issues is the failure mode this skill exists to prevent.

After approval, create them, then report back the numbers and labels.

## Cross-references

When issues relate, say so *inside* the bodies: dependencies ("blocked until #N
lands"), overlaps ("#N touches the same lines; rebase over it"), and interim
fixes ("#N eventually supersedes this"). Contributors cannot see your mental
model of the backlog.
