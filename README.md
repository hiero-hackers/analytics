# Analytics

[![Tests](https://github.com/hiero-hackers/analytics/actions/workflows/test.yml/badge.svg)](https://github.com/hiero-hackers/analytics/actions/workflows/test.yml)
[![Lint](https://github.com/hiero-hackers/analytics/actions/workflows/lint.yml/badge.svg)](https://github.com/hiero-hackers/analytics/actions/workflows/lint.yml)
[![CodeQL](https://github.com/hiero-hackers/analytics/actions/workflows/codeql.yml/badge.svg)](https://github.com/hiero-hackers/analytics/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/hiero-hackers/analytics/badge)](https://securityscorecards.dev/viewer/?uri=github.com/hiero-hackers/analytics)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

## Overview

Stay up to date with hiero organisation activity and contributor diversity

This repository provides analytics for the [Hiero repositories](https://github.com/hiero-ledger).

**Latest dashboard:** [hiero-hackers.github.io/analytics](https://hiero-hackers.github.io/analytics/)

**Contributing?** Start with the [contributor guide](CONTRIBUTING.md) — setup, workflow, skill levels, AI policy, and testing conventions.

## Quickstart

**Prerequisites:** [Git](https://git-scm.com/downloads), Python 3.11+, and
[uv](https://docs.astral.sh/uv/getting-started/installation/). `uv` provisions the
right Python version and all dependencies for you.

```bash
git clone https://github.com/hiero-hackers/analytics.git
cd analytics
uv sync          # create the environment and install everything
uv run pytest    # verify — no credentials needed
```

Most work, and the whole test suite, runs without credentials. For pipelines that
fetch **live** GitHub data, add a `.env` file in the project root with a token that
has public-repo read access (this only raises your API rate limit):

```bash
GITHUB_TOKEN=<your token>
```

**Contributing?** The [contributor guide](CONTRIBUTING.md) has the full setup, the
fork workflow, linting and pre-commit, skill levels, and testing conventions.

## Running the Analytics

With your `GITHUB_TOKEN` configured (see [Quickstart](#quickstart)), run **every** analytics pipeline with a single command:

```bash
uv run hiero-analytics
```

**What this does:**
- Runs all analytics pipelines in one process (one Python start-up instead of one per pipeline), reusing the on-disk fetch cache between pipelines
- Writes charts to `outputs/charts/` and data tables to `outputs/data/`
- Isolates failures — if one pipeline errors it is logged and the rest still run; the command exits non-zero if any failed

For faster local debugging, run the explicit `all` command with `--fail-fast`:

```bash
uv run hiero-analytics all --fail-fast
```

This stops after the first pipeline failure and exits non-zero immediately, so
the original traceback is not buried beneath output from later pipelines.
Without `--fail-fast`, the default behaviour is unchanged: failures are logged,
the remaining pipelines continue, and all failures are reported at the end.

Everything under `outputs/` is generated and gitignored. The scheduled workflow publishes the dashboard to GitHub Pages instead of committing generated charts and reports.

This is the same command the scheduled **Refresh Analytics Data** workflow runs.

> ⏱️ **The first run is slow.** It fetches org-wide activity from the GitHub API (subject to rate limits), so the initial run can take **several minutes**. Later runs are incremental and much faster (see [Incremental data fetching](#incremental-data-fetching)).

### Viewing the dashboard

**Just want to look?** The latest refresh is published to GitHub Pages — open **https://hiero-hackers.github.io/analytics/** to view it in your browser, no clone or setup required. The scheduled **Refresh Analytics Data** workflow rebuilds and republishes it automatically.

The dashboard is a static Vite + React app in `web/` that renders the versioned
JSON data API (`outputs/data/api/v1/`) — it is **built from the generated
data**, so generate the data first or the dashboard will be empty.
`uv run hiero-analytics` already emits the API as its **last** step, so on a
fresh checkout that one command gives you data *and* a populated dashboard. To
develop locally:

```bash
uv run hiero-analytics data_api        # re-emit the API from existing outputs
python3 -m http.server 8642 -d outputs # serve data + charts (dev proxy target)
npm run dev --prefix web               # the app, on http://localhost:5173
```

New sections, charts, and orgs appear in the app automatically — it renders
whatever the API manifest lists (one tab per organization that has data), so
adding analytics rarely requires frontend changes.

### Tracing a chart or table back to its data

Nothing generated is committed, and each Pages deploy replaces the last, so every artifact carries its own provenance instead:

- **Charts** have a footer reading `data <watermark> · code <revision> · n=<rows>`. A `-dirty` suffix on the revision means the chart was drawn from uncommitted code and cannot be reproduced from any commit.
- **The dashboard** stamps the same revision in its page footer (from the API manifest's provenance block), plus a per-section *data as of* badge.
- **CSVs on disk** (`outputs/data/`) keep their provenance in a `<name>.csv.meta.json` sidecar — `generated_at`, `git_sha`, `record_count`. The CSV body is left clean so `pd.read_csv` works unchanged.
- **Each scheduled run** archives its dataset snapshot as a `dataset-snapshot-<run>-<sha>` workflow artifact, including a `SNAPSHOT.json` manifest of per-dataset watermarks and SHA-256s.

**Downloading a table as CSV** from the dashboard writes `#` comment lines above the header, naming the view, the data watermark, and the revision. The export takes the rows currently *visible*, so filtering before you download gives you a subset — the preamble says so (`# 2 of 7 rows (filtered view)`).

Those comment lines mean a downloaded file needs the `comment` flag when read programmatically:

```bash
python -c "import pandas as pd; print(pd.read_csv('maintainers.csv', comment='#'))"
```

Without it pandas raises `ParserError` rather than mis-reading the header. Spreadsheet apps open the file fine, showing the preamble as four leading text rows. This applies only to browser downloads — the CSVs under `outputs/data/` have no preamble.

### Pull request dashboard previews

Pull requests that change analytics code build the full site (data API + web app + charts) and upload it as a **dashboard-preview** workflow artifact. Download and unzip it, then serve the folder:

```bash
python3 -m http.server -d .
```

Open the URL it prints (`http://localhost:8000/`). A server is needed because the app fetches its JSON over HTTP, so opening `index.html` from the filesystem won't load data. The artifact is built from the pull request's own code — treat it as you would any other contributor-authored code.

Most previews restore the latest base-branch datasets and set `HIERO_ANALYTICS_OFFLINE=1`. This keeps the input data fixed so the artifact isolates code changes. Offline mode never falls back to a network fetch: it fails clearly when a required dataset or governance snapshot is missing. Pipelines backed only by live repo or third-party APIs are skipped, so Scorecard, CODEOWNERS/runner, repo-only, and Hiero Hackers sections may be absent from an offline preview.

Changes to the field-bearing ingestion layer (`data_sources/models.py`, `github_ingest/`, the queries, the governance snapshot) automatically use a live fetch, because a cached dataset cannot contain newly introduced fields; transport-only changes (client, rate limiting) keep the fast offline path. Those fields are populated only for records fetched during the preview; the scheduled refresh remains responsible for a complete backfill. Preview workflows restore caches but never save them.

### Running a single pipeline

The same `hiero-analytics` CLI runs each pipeline as a subcommand:

```bash
uv run hiero-analytics scorecard
```

Repo-scoped pipelines accept `--org` and `--repo` (defaulting to the configured `GITHUB_ORG` / `GITHUB_REPO`); run `uv run hiero-analytics <command> --help` to see a subcommand's options. Each pipeline lives in `src/hiero_analytics/pipelines/<command>.py` and is declared in the registry in `src/hiero_analytics/pipelines/__init__.py`.

Available pipelines:

| Command | What it produces |
|---|---|
| `difficulty` | Issue difficulty distribution |
| `difficulty_over_time` | Difficulty trend over time |
| `onboarding` | Onboarding signal (issues vs. contributors) |
| `contributor_profiles` | Per-contributor profiles |
| `maintainer_pipeline` | Maintainer pipeline by governance role |
| `contributor_activity` | Org-wide contributor activity tables |
| `contributor_heatmap` | Contributor activity heatmaps |
| `role_coverage` | Governance roles vs. real activity per repo |
| `affiliation` | Contributor affiliation mapping |
| `scorecard` | OpenSSF Scorecard results |
| `codeowner_and_runner` | CODEOWNERS presence and CI runner usage |
| `hiero_hackers` | Hiero Hackers org composition and activity |
| `hip_implementation` | Maps HIPs to the PRs that reference them across the org — feeds the HIPs dashboard tab |
| `repo_growth` | Generate repository-growth timeline charts |
| `data_api` | Emits the versioned JSON data API (`outputs/data/api/v1/`) the web dashboard renders — the full run does this last |
| `discord_analytics` | Discord analytics — needs manual CSV inputs, so not part of the full run |
| `contributor_churn` | Contributor churn analysis — on-demand, not part of the full run |
| `build_affiliations` | Regenerates the curated `affiliations.yaml` from public signals — maintenance tool, needs `gpg` |

> Fetched GitHub data is cached under `outputs/cache/` for 24 hours, so repeated runs within a day reuse it instead of re-querying the API.

### Incremental data fetching

To avoid re-downloading all of GitHub history on every run, fetching is **incremental**:

- The **first run** does a full fetch and stores a dataset under `outputs/data/datasets/` (this run is the slow one).
- **Later runs** fetch only what changed since the last run and merge it in — much faster.
- Every 30 days (or with `refresh=True`) it does a full re-fetch to self-heal, so missed updates or deleted items can't accumulate.

**The datasets are not committed to git** — they're gitignored. Persistence is handled differently per environment:

- **Locally:** the dataset lives on your disk under `outputs/data/datasets/`. Nothing to set up — just run the pipeline. To force a clean rebuild, delete that folder.
- **In CI:** the scheduled workflow persists the dataset between runs via `actions/cache` (see `.github/workflows/update-analytics.yml`). If the cache is ever evicted, the next run simply does one full fetch and then resumes incrementally.

> Local and CI datasets are independent — each maintains its own and stays correct on its own; you never need to sync them.

---

## Documentation

- [**Architecture**](docs/architecture.md) — the layer map, the two extensibility registries, the fetch/persistence model, and where new features go. Start here to understand the codebase.
- [**Role-holder affiliations**](docs/affiliations.md) — how each maintainer and committer is mapped to an organisation, how to make manual corrections, and how to resolve the unknowns.
- [**Snapshot archive**](docs/snapshots.md) — every refresh's data API is archived to the `data/snapshots` branch, so the dashboard's history is queryable and diffable. How to read a past snapshot, and how to build on it.

---

## License

- Available under the **Apache License, Version 2.0 (Apache-2.0)*
