# Role-holder affiliations

How the analytics decides **which organisation each governance role-holder belongs to**, and
how to correct it by hand. This powers the *Organisation diversity* charts and tables in the
dashboard (who employs the maintainers and the committers, per-repo and per-team
concentration, the activity heatmaps by organisation, and the affiliations reference tables).

## Source of truth

Two files hold the mapping, and only one of them is edited by hand:

| File | Written by | Edit it? |
|---|---|---|
| [`affiliations.yaml`](../src/hiero_analytics/data/affiliations.yaml) | `hiero-analytics build_affiliations`, from public signals | **No** — it is generated, and the next regeneration overwrites it |
| [`affiliation_overrides.yaml`](../src/hiero_analytics/data/affiliation_overrides.yaml) | maintainers | **Yes** — every hand correction lives here |

At run time the two are merged and **the overrides win** wherever both name a login. The
dashboard reads them directly (offline) — no network needed at render time.

The generated file has one row per governance participant:

```yaml
acuarica: "Hashgraph"            # maintainer · Luis Mastrangelo
aceppaluni: "Independent"        # maintainer
daniela-barbosa: "?"             # maintainer · Daniela Barbosa
```

- **Value** — an organisation name, `"Independent"` (a solo contributor with no employer),
  or `"?"` (unknown — no public signal yet).
- **Comment** — `governance-role · name`, for readability. The role tag (`maintainer` /
  `committer` / `triage` / `team`) is informational; the charts derive each person's role
  from the live governance config, not from this comment.

The overrides file has one row per lowercase login, and the reason is part of the row:

```yaml
login: "Organisation"  # evidence — who checked, what they saw, when
```

The *Organisation diversity* charts are split into **role tabs**. Each tab draws a disjoint
population, keyed on the person's *highest* role anywhere in the org, so nobody is counted
twice: the maintainers on the Maintainers tab, and the people whose ceiling is write access on
the Committers tab. Curation coverage differs between them — committers are usually the thinner
of the two — and the dashboard's Governance tab shows the current population sizes and resolved
shares. The employer pie shows only resolved holders, so its percentages use the same
resolved-population denominator as the concentration metrics. Unresolved holders remain visible
in the affiliations and diversity tables, and each pipeline run logs the known share and warns if
it falls below the configured floor.

## How affiliations are resolved (automated)

The generated file is produced by
[`hiero-analytics build_affiliations`](../src/hiero_analytics/pipelines/build_affiliations.py),
which resolves each person from public GitHub signals in **priority order**:

1. **GPG-key email** — the work email on their published signing key (`github.com/<login>.gpg`)
2. **profile email**
3. **MAINTAINERS.md** — the project's own `Company Affiliation` column
4. **GitHub company field** (also catches a clean external employer, e.g. `Robinhood`)
5. **profile bio** — a single `@ Company` mention (several `@`s read as interests, ignored)
6. **public org membership**
7. **solo domain** — only a *curated* small-company domain becomes a named org
8. **commit-author email** — last-resort, mined from the commit API

Rules baked in:

- **Obfuscated `users.noreply.github.com` addresses never count** — they tell us nothing.
- **Lineage:** *Swirlds Labs* is counted as its present-day name **Hashgraph**; **Hedera** and
  **Hgraph** are kept as separate entities.
- A current external company (a real employer in the company field) outranks a *stale*
  ecosystem signal (e.g. an old commit email).
- Two genuinely-different employer emails on one key are broken by the **most recent signed
  commit**.

The **`method`** column in the affiliations reference table shows `automated` (the resolver
placed them) vs `manual` (the login has a row in `affiliation_overrides.yaml` — see below).

## Making a manual correction

Add a row to
[`affiliation_overrides.yaml`](../src/hiero_analytics/data/affiliation_overrides.yaml), or edit
the login's existing row there. There is no marker to append; the row itself is the
correction. Use the lowercase login, set the value, and give the **reason as the trailing
comment** — a test fails on a row without one.

```yaml
diegoescalonaro: "The Hashgraph Association"  # says so on profile
jane-doe: "Independent"                       # no employer; confirmed with them on the TSC call
john-roe: "?"                                 # resolver guessed the wrong employer; right one unknown
```

The value is an organisation name, `"Independent"`, or `"?"`. Use **`"?"`** to *unset* a wrong
resolver guess when you know it is wrong but not what is right: the person then counts as
unknown instead of being credited to the wrong employer.

An override row:

- **wins over every automated signal**,
- **survives regeneration** — `build_affiliations` never reads or rewrites the overrides file,
- **survives the person leaving the roster** — the row stays until someone deletes it, so a
  contributor who steps down and comes back, or moves to another org we track, keeps the
  correction (see [Regenerating the data](#regenerating-the-data) for how strays are flagged),
- reads **`manual`** in the reference table.

> ⚠️ Do not edit a value in `affiliations.yaml` itself. It is overwritten on the next
> regeneration, and the generator refuses to run while any row there still carries a
> `# manual` marker from the old convention — it names the rows so you can move each one to the
> overrides file first.

## Resolving the unknowns

The unknowns are the rows resolved to `"?"` (status `unknown`). To work through them:

1. **Get the worklist** — filter the *Maintainer affiliations* or *Committer affiliations*
   table by `status = unknown`, or `grep ': "?"' src/hiero_analytics/data/affiliations.yaml`.
   Each row's comment has the name. The committer roster is where the bulk of the remaining
   unknowns sit, so check its known share before interpreting the Committers pie.
2. **Find their employer** — check the gitignored audit CSV
   (`outputs/data/org/<org>/maintainer_affiliation_audit.csv`); it lists each unknown's weak
   signals: an unmapped org membership, a **LinkedIn URL** pointer, redacted email domains.
   The scheduled refresh (below) uploads the same CSV as a workflow artifact. Otherwise, ask
   the TSC or open a *Suggest a correction* issue from the dashboard.
3. **Record it** — add a row for the login to `affiliation_overrides.yaml` with the employer as
   the value and the evidence as the reason comment. It's now locked and reads `manual`.

Hand-resolved unknowns are permanent, so the unknown count only goes down as people curate.

## Regenerating the data

`build_affiliations` refreshes the generated YAML from live signals. It needs a `GITHUB_TOKEN`,
the `gpg` CLI, and network access — so it is a **maintenance tool, not part of the dashboard
pipeline**.

```bash
GITHUB_TOKEN=… uv run hiero-analytics build_affiliations
```

It rewrites `affiliations.yaml` (pure resolver output; it never touches the overrides file) and
writes a provenance audit CSV to the gitignored `outputs/` tree. It also warns about any row in
the overrides file whose login no governance roster names. Those rows are kept on purpose, so
prune or keep each one deliberately.

### The scheduled refresh

The [`refresh-affiliations.yml`](../.github/workflows/refresh-affiliations.yml) workflow runs
the generator on the **1st of each month at 06:00 UTC**, and on demand from the Actions tab
(manual dispatch). Each run:

- uploads the audit CSV as a workflow artifact named `affiliation-audit-<run id>`, kept for
  30 days, and
- opens a pull request from the branch `chore/refresh-affiliations` that touches **only**
  `affiliations.yaml`.

To review it, read the PR's diff with the run's audit artifact beside it:

- **People joining or leaving** — rows appear and disappear as the governance config changes;
  check the role tags in the comments moved with the config.
- **A value that flipped** — especially an organisation turning into `?` (the signal that
  supported it is gone) or one employer replacing another. The audit CSV shows which signal
  decided each row, so you can tell a real job change from a lost signal.
- **Stray overrides** — the run's log lists override logins that no roster names. Prune the
  ones that no longer matter; leave the rest.

If a generated value is wrong and you know the answer, do not edit the PR's file: add the
correction to `affiliation_overrides.yaml` in its own pull request. Then merge the refresh.

## Privacy

A person's **full email address is never written to disk**. Resolution uses full addresses in
memory (for domain matching, lineage, the noreply rule), but the audit CSV logs only the
**domain** (`@gmail.com`, `@swirldslabs.com`). The committed YAML files and the dashboard's
per-person table carry only `login → organisation` — no emails at all. The audit CSV itself is
gitignored, and the workflow artifact is the same file, deleted after 30 days.
