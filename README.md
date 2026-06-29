# Analytics

## Overview

Stay up to date with hiero organisation activity and contributor diversity

This repository provides analytics for the [Hiero repositories](https://github.com/hiero-ledger).

## Setting Up Analytics Development

## Repository Setup

Before you begin, make sure you have:
- **Git** installed ([Download Git](https://git-scm.com/downloads))
- **Python 3.10+** installed ([Download Python](https://www.python.org/downloads/))
- A **GitHub account** ([Sign up](https://github.com/join))

### Step 1: Fork the Repository

Forking creates your own copy of the Hiero Python SDK that you can modify freely.

1. Go to [https://github.com/hiero-hackers/analytics](https://github.com/hiero-hackers/analytics)
2. Click the **Fork** button in the top-right corner
3. Select your GitHub account as the destination

You now have your own fork at `https://github.com/YOUR_USERNAME/hiero-hackers/analytics`

### Step 2: Clone Your Fork

Clone your fork to your local machine:

```bash
git clone https://github.com/YOUR_USERNAME/hiero-hackers/analytics.git
cd hiero-hackers/analytics
```

Replace `YOUR_USERNAME` with your actual GitHub username.

### Step 3: Add Upstream Remote

Connect your local repository to the original repository. This allows you to keep your fork synchronized with the latest changes.

```bash
git remote add upstream https://github.com/hiero-hackers/analytics.git
```

**What this does:**
- `origin` = your fork (where you push your changes)
- `upstream` = the original repository (where you pull updates from)

### Step 4: Verify Your Remotes

Check that both remotes are configured correctly:

```bash
git remote -v
```

You should see:
```
origin    https://github.com/YOUR_USERNAME/hiero-hackers/analytics.git (fetch)
origin    https://github.com/YOUR_USERNAME/hiero-hackers/analytics.git (push)
upstream  https://github.com/hiero-hackers/analytics.git (fetch)
upstream  https://github.com/hiero-hackers/analytics.git (push)
```

---

## Installation

#### Install uv

**On macOS/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**On macOS (using Homebrew):**
```bash
brew install uv
```

**On Windows:**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Other installation methods:** [uv Installation Guide](https://docs.astral.sh/uv/getting-started/installation/)

#### Verify Installation

```bash
uv --version
```

## Install Dependencies

`uv` automatically manages the correct Python version based on the `.python-version` file in the project, so you don't need to worry about version conflicts.

Install project dependencies:

```bash
uv sync
```

**What this does:**
- Downloads and installs the correct Python version (if needed)
- Creates a virtual environment
- Installs all project dependencies
- Installs development tools (pytest, ruff, etc.)

## Environment Setup

Create a fine-grained personal access token [Personal Acess Tokens Info](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) and [Create Personal Access Token](https://github.com/settings/personal-access-tokens). Enable it for public repositorites and do not enable any extra access.

Create a `.env` file in the project root, copy and save your token.

```bash
GITHUB_TOKEN=yours
```

You'll need this token to increase your API rate limit when interacting with Github data. 

### Test Setup

Run the test suite to ensure everything is working:

```bash
uv run pytest
```
---

## Running the Analytics

With your `GITHUB_TOKEN` configured (see [Environment Setup](#environment-setup)), run **every** analytics pipeline with a single command:

```bash
uv run hiero-analytics
```

**What this does:**
- Runs all analytics pipelines in one process (one Python start-up instead of one per pipeline), reusing the on-disk fetch cache between pipelines
- Writes charts to `outputs/charts/` and data tables to `outputs/data/`
- Isolates failures — if one pipeline errors it is logged and the rest still run; the command exits non-zero if any failed

This is the same command the scheduled **Refresh Analytics Data** workflow runs.

> ⏱️ **The first run is slow.** It fetches org-wide activity from the GitHub API (subject to rate limits), so the initial run can take **several minutes**. Later runs are incremental and much faster (see [Incremental data fetching](#incremental-data-fetching)).

### Viewing the dashboard

**Just want to look?** The latest refresh is published to GitHub Pages — open **https://hiero-hackers.github.io/analytics/** to view it in your browser, no clone or setup required. The scheduled **Refresh Analytics Data** workflow rebuilds and republishes it automatically.

To build it yourself, the single-file dashboard at `outputs/dashboard.html` is **built from the generated data** — it reads the tables in `outputs/data/` and the charts in `outputs/charts/`. Because of that:

- **Generate the data first, or the dashboard will be empty.** Building the dashboard with no data produces a page with nothing in it. `uv run hiero-analytics` already builds the dashboard as its **last** step, so on a fresh checkout that one command gives you data *and* a populated dashboard.
- **To rebuild only the dashboard** once the data already exists (e.g. after tweaking a label), run:

  ```bash
  uv run python -m hiero_analytics.run_dashboard
  ```

- Open `outputs/dashboard.html` in any browser — it's fully self-contained (no server required) and shows one tab per organization that has data.

### Running a single pipeline

To run just one pipeline, invoke its module directly:

```bash
uv run python -m hiero_analytics.run_gfic_gfi_org
```

Available pipelines:

| Module | What it produces |
|---|---|
| `run_gfic_gfi_org` | Good First Issue / onboarding pipeline |
| `run_difficulty_org_for_repo` | Issue difficulty distribution |
| `run_onboarding_signal_for_repo` | Onboarding signal (issues vs. contributors) |
| `run_contributor_profiles_repo` | Per-contributor profiles |
| `run_maintainer_pipeline_org` | Maintainer pipeline by governance role |
| `run_scorecard_for_org` | OpenSSF Scorecard results |
| `run_codeowner_and_runner` | CODEOWNERS presence and CI runner usage |
| `run_hiero_hackers_org` | Hiero Hackers org composition and activity |

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

## License

- Available under the **Apache License, Version 2.0 (Apache-2.0)*
