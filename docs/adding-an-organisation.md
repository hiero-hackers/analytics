# Adding an organisation

The dashboard renders every organisation in the org registry,
`src/hiero_analytics/config/orgs.py`. Adding one is a single `OrgProfile` there;
pipelines, dashboard tabs, the data API and the web app all follow from it.
This page is the checklist, and explains what each choice on the profile does.

## 1. Try it first (optional, no code)

Run the scheduled workflow once with the candidate org, before anything is
committed:

1. Open **Actions → Refresh Analytics Data → Run workflow**.
2. Put the org's login in **trial_orgs** (comma-separated for several).
3. When the run finishes, read its **GitHub API usage** table in the job summary,
   and download the `github-pages` artifact to look at the org's tab locally
   (`python3 -m http.server -d .` inside the unzipped folder).

A trial run never deploys, archives, or saves the dataset cache. A trial org runs every pipeline that
needs no capability (contributors, issues and onboarding, security and
scorecards, releases, repository growth, and the detail views), as an
ungoverned org. Locally, the same thing is:

```bash
HIERO_ANALYTICS_TRIAL_ORGS=<login> uv run hiero-analytics
```

A large org's first fetch can take hours under the Actions token, so try it
under `ANALYTICS_PAT`, which the workflow prefers when it is configured. See
[api-budget.md](api-budget.md) for what an org costs.

## 2. Register it

Append one profile to `ORGS` in `src/hiero_analytics/config/orgs.py`:

```python
OrgProfile(
    name="LFDT-EXAMPLE",  # GitHub's exact spelling (checked before every run)
    display_name="LFDT Example",  # optional: the switcher label; the login otherwise
    extra=True,  # rendered by the scheduled run
)
```

Then add what the org actually provides:

| Field | Set it when | What the org gets |
|---|---|---|
| `governed=True`, `governance_url=...` | The org publishes a governance file with `teams:` and `repositories:` (the shape of hiero-ledger's `config.yaml`) | The Governance tab: role coverage, maintainer pipeline, teams, organisation diversity, role networks; role labels on the activity heatmap |
| `blanket_teams=frozenset({...})` | The governance file grants some teams on (nearly) every repo, such as staff or admin teams | Those teams stop counting as every repo's maintainers |
| `org_overview=True` | The org is a loose collection of projects worth an overview card | The org-overview card (repositories by contributors, languages, recent pushes) |
| `hip_proposals_repo="owner/repo"` | The org tracks improvement proposals in a repository | The HIPs tab |
| `discord=True` | The manual Discord export belongs to this org | The Community tab (one org only) |
| `brand="<key>"` | Maintainers approved a logo | That logo top left while the org is selected (step 3) |
| `repo_categories={...}` | Some repos land in the wrong category in the networks | Per-repo category overrides, by bare repo name |

Leave out what does not apply: a capability the org lacks only hides the tabs
that need it, and each hidden tab explains why.

## 3. Logo (optional)

Put `logo.svg` (light theme) and `logo-dark.svg` (dark theme) under
`web/public/brand/<key>/`, set `brand="<key>"` on the profile, and record the
artwork's source in `web/public/brand/README.md`. Without a logo, or if a file
fails to load, the dashboard shows the Hiero mark.

## 4. If it is governed

Resolve its people's employers for the organisation-diversity charts:

```bash
uv run hiero-analytics build_affiliations
```

This regenerates `src/hiero_analytics/data/affiliations.yaml` from every
governed org's config. Review the new rows and hand-correct the unknowns as
[affiliations.md](affiliations.md) describes. Until then the run logs an
affiliation-coverage warning for the org, and its diversity charts describe
only the people already resolved.

## 5. Open the pull request

The change should touch `config/orgs.py`, and optionally the logo files and
`affiliations.yaml`, and nothing else. CI checks that:

- no other file names the org (`tests/test_org_literals.py`);
- dashboard cards are keyed by capability, never by org name
  (`tests/dashboard_spec/test_spec_consistency.py`);
- the dashboard preview fetches live data, because a change to the registry
  switches it out of offline mode (the base branch's cache has no data for the
  new org).

After merge, the next nightly refresh (01:00 UTC) fetches the org from scratch
and publishes its tab. Its first run costs more than later ones; the job
summary shows both.

## What happens when it fails

A pipeline failure in an extra org is listed in the job summary and in the run's
`SNAPSHOT.json`, but does not fail the run: the dashboard still publishes. The
sections that pipeline feeds are missing for that org until a later run
succeeds (CI caches the fetched datasets between runs, not the generated
tables), and a tab left with nothing shows its "no data for this org" note. A failure in the primary org, or in the data API, still fails the run and
keeps the last good deploy. Pull request previews run with `--strict`, so a
change that breaks any org goes red there.

Before fetching, every run checks each login against GitHub. A login that does
not exist, or that GitHub spells differently (`lfdt-example` for
`LFDT-EXAMPLE`), is skipped with a `preflight[<org>]` failure, because output
paths and `owner/repo` joins are case-sensitive. If the lookup itself fails (a network
error), the run logs a warning and fetches the org anyway.

## Removing an organisation

Delete its profile. The next complete run prunes its datasets from the cache
(`dataset_store.prune_untouched_datasets`), so adding it back later costs a full
fetch again.
The data API publishes only the orgs the current configuration renders, so an
old output directory left in a local `outputs/` (from a removed org or a past
trial) is ignored rather than shown.
