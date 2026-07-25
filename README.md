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

Everything under `outputs/` is generated and gitignored. The scheduled workflow publishes the dashboard to GitHub Pages instead of committing generated charts and reports.

This is the same command the scheduled **Refresh Analytics Data** workflow runs.

> ⏱️ **The first run is slow.** It fetches org-wide activity from the GitHub API (subject to rate limits), so the initial run can take **several minutes**. Later runs are incremental and much faster (see [Incremental data fetching](#incremental-data-fetching)).

### Viewing the dashboard

**Just want to look?** The latest refresh is published to GitHub Pages — open **https://hiero-hackers.github.io/analytics/** to view it in your browser, no clone or setup required. The scheduled **Refresh Analytics Data** workflow rebuilds and republishes it automatically.

To build it yourself, the single-file dashboard at `outputs/dashboard.html` is **built from the generated data** — it reads the tables in `outputs/data/` and the charts in `outputs/charts/`. Because of that:

- **Generate the data first, or the dashboard will be empty.** Building the dashboard with no data produces a page with nothing in it. `uv run hiero-analytics` already builds the dashboard as its **last** step, so on a fresh checkout that one command gives you data *and* a populated dashboard.
- **To rebuild only the dashboard** once the data already exists (e.g. after tweaking a label), run:

  ```bash
  uv run hiero-analytics dashboard
  ```

- Open `outputs/dashboard.html` in any browser — it's fully self-contained (no server required) and shows one tab per organization that has data.

### Tracing a chart or table back to its data

Nothing generated is committed, and each Pages deploy replaces the last, so every artifact carries its own provenance instead:

- **Charts** have a footer reading `data <watermark> · code <revision> · n=<rows>`. A `-dirty` suffix on the revision means the chart was drawn from uncommitted code and cannot be reproduced from any commit.
- **The dashboard** stamps the same revision in its header, plus a per-section *data as of* badge.
- **CSVs on disk** (`outputs/data/`) keep their provenance in a `<name>.csv.meta.json` sidecar — `generated_at`, `git_sha`, `record_count`. The CSV body is left clean so `pd.read_csv` works unchanged.
- **Each scheduled run** archives its dataset snapshot as a `dataset-snapshot-<run>-<sha>` workflow artifact, including a `SNAPSHOT.json` manifest of per-dataset watermarks and SHA-256s.

**Downloading a table as CSV** from the dashboard writes four `#` comment lines above the header, naming the view, the data watermark, the revision, and the row count. The export takes the rows currently *visible*, so filtering before you download gives you a subset — the preamble says so (`# 2 of 7 rows (filtered: "sdk-j")`).

Those comment lines mean a downloaded file needs the `comment` flag when read programmatically:

```bash
python -c "import pandas as pd; print(pd.read_csv('maintainers.csv', comment='#'))"
```

Without it pandas raises `ParserError` rather than mis-reading the header. Spreadsheet apps open the file fine, showing the preamble as four leading text rows. This applies only to browser downloads — the CSVs under `outputs/data/` have no preamble.

### Pull request dashboard previews

Pull requests that change analytics code build `outputs/dashboard.html` and upload it as a **dashboard-preview** workflow artifact. Download that single HTML file to review the PR's charts and tables without committing generated PNGs or reports.

Most previews restore the latest base-branch datasets and set `HIERO_ANALYTICS_OFFLINE=1`. This keeps the input data fixed so the artifact isolates code changes. Offline mode never falls back to a network fetch: it fails clearly when a required dataset or governance snapshot is missing. Pipelines backed only by live repo or third-party APIs are skipped, so Scorecard, CODEOWNERS/runner, repo-only, and Hiero Hackers sections may be absent from an offline preview.

Changes under `src/hiero_analytics/data_sources/` automatically use a live fetch because a cached dataset cannot contain newly introduced fields. Those fields are populated only for records fetched during the preview; the scheduled refresh remains responsible for a complete backfill. Preview workflows restore caches but never save them.

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
| `dashboard` | Rebuilds `outputs/dashboard.html` from existing data (the full run does this last) |
| `discord_analytics` | Discord analytics — needs manual CSV inputs, so not part of the full run |
| `contributor_churn` | Contributor churn analysis — on-demand, not part of the full run |
| `build_affiliations` | Regenerates the curated `affiliations.yaml` from public signals — maintenance tool, needs `gpg` |
| `hip_implementation` | Maps HIPs to the PRs that reference them across the org — feeds the HIPs dashboard tab |

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
- [**Maintainer affiliations**](docs/affiliations.md) — how each maintainer is mapped to an organisation, how to make manual corrections, and how to resolve the unknowns.

---

## License

- Available under the **Apache License, Version 2.0 (Apache-2.0)*
