# Maintainer affiliations

How the analytics decides **which organisation each maintainer belongs to**, and how to
correct it by hand. This powers the *Organisation diversity* charts and tables in the
dashboard (who employs the maintainers, per-repo and per-team concentration, the activity
heatmaps by organisation, and the affiliations reference table).

## Source of truth

[`src/hiero_analytics/data/affiliations.yaml`](../src/hiero_analytics/data/affiliations.yaml)
is the single source of truth. One row per governance participant:

```yaml
acuarica: "Hashgraph"            # maintainer · Luis Mastrangelo
aceppaluni: "Independent"        # maintainer
daniela-barbosa: "?"             # maintainer · Daniela Barbosa
```

- **Value** — an organisation name, `"Independent"` (a solo contributor with no employer),
  or `"?"` (unknown — no public signal yet).
- **Comment** — `governance-role · name`, for readability. The role tag (`maintainer` /
  `committer` / `triage` / `team`) is informational; only the **104 maintainers** feed the
  maintainer-org charts, the rest are here so the team-concentration view is fully covered.

The dashboard reads this file directly (offline) — no network needed at render time.

## How affiliations are resolved (automated)

The file is **seeded** by [`examples/build_affiliations.py`](../examples/build_affiliations.py),
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
placed them) vs `manual` (a hand-correction — see below).

## Making a manual correction

Edit the row in `affiliations.yaml`: change the value and append **`# manual`** (optionally a
reason). It can go after the role comment.

```yaml
diegoescalonaro: "Telefónica"   # manual: Telefónica blockchain team
popowycz: "Hedera"              # maintainer · manual
```

A manual row:

- **wins over every automated signal**,
- **survives regeneration** — `build_affiliations.py` re-emits it as
  `# MANUAL — reason (resolver: <its competing guess>)` and never overwrites it,
- reads **`manual`** in the reference table.

> ⚠️ A value you change **without** `# manual` will revert to the resolver's guess on the next
> regeneration. Always add the marker to make a hand-edit stick.

## Resolving the unknowns

The unknowns are the `"?"` rows (status `unknown`). To work through them:

1. **Get the worklist** — filter the *Maintainer affiliations* table by `status = unknown`, or
   `grep ': "?"' src/hiero_analytics/data/affiliations.yaml`. Each row's comment has the name.
2. **Find their employer** — check the gitignored audit CSV
   (`outputs/data/org/<org>/maintainer_affiliation_audit.csv`); it lists each unknown's weak
   signals: an unmapped org membership, a **LinkedIn URL** pointer, redacted email domains.
   Otherwise, ask the TSC or open a *Suggest a correction* issue from the dashboard.
3. **Record it** — set the value and append `# manual: <evidence>`. It's now locked and reads
   `manual`.

Hand-resolved unknowns are permanent, so the unknown count only goes down as people curate.

## Regenerating the data

`build_affiliations.py` refreshes the YAML from live signals. It needs a `GITHUB_TOKEN`, the
`gpg` CLI, and network access — so it is a **maintenance tool, not part of the dashboard
pipeline**.

```bash
GITHUB_TOKEN=… uv run python examples/build_affiliations.py
```

It rewrites `affiliations.yaml` (preserving all `# manual` rows) and writes a provenance audit
CSV to the gitignored `outputs/` tree.

## Privacy

A person's **full email address is never written to disk**. Resolution uses full addresses in
memory (for domain matching, lineage, the noreply rule), but the audit CSV logs only the
**domain** (`@gmail.com`, `@swirldslabs.com`). The committed YAML and the dashboard's
per-person table carry only `login → organisation` — no emails at all. The audit CSV itself is
gitignored.
