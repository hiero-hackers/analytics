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

## License

- Available under the **Apache License, Version 2.0 (Apache-2.0)*
