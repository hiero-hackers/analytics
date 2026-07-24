# Config Module

The `config` module contains shared configuration used across the analytics project.
It centralizes constants, environment settings, and formatting utilities so that behaviour and styling remain consistent throughout the codebase.

Keeping configuration in one place improves maintainability, avoids duplication, and makes it easier to adjust behaviour without modifying core logic.

---

## Overview

The module provides configuration for:

* **Chart formatting** – reusable title helpers and visual style constants
* **GitHub API access** – authentication, endpoints, and request behaviour
* **Project paths** – standard directories for outputs, data, charts, and caching

---

## Modules

### `chart_labels.py`

Provides helper functions for generating consistent chart titles.

Functions include:

* `label_yearly(label)`
  Generates titles such as `"Commits per Year"`.

* `label_total_by_repo(label)`
  Generates titles such as `"Pull Requests by Repository"`.

* `pipeline(label_a, label_b)`
  Generates titles such as `"Issues → Closed Issues Pipeline"`.

Charts should provide flexibility to name them as you'd like.
These helpers make it easier for titles to be consistent across the analytics codebase.

---

### `chart_style.py`

Defines constants controlling the appearance of charts.

Configuration includes:

* Default figure size and resolution
* Default plotting style
* Font sizes for titles, labels, ticks, and legends
* Grid visibility and formatting

These settings ensure charts share a consistent visual style across the project.

---

### `github.py`

Configuration for interacting with the GitHub API.

Key settings include:

* `BASE_URL` – GitHub API endpoint
* `GITHUB_TOKEN` – optional authentication token loaded from environment variables
* `HTTP_TIMEOUT_SECONDS` – request timeout
* `REQUEST_DELAY_SECONDS` – delay between API calls

The module also provides:

* `github_headers()` – returns request headers for authenticated API calls.

If a `GITHUB_TOKEN` is not provided, the API will operate under GitHub’s unauthenticated rate limit.

---

### `paths.py`

Defines project directory locations used by the analytics pipeline.

Important paths:

* `PROJECT_ROOT`
* `OUTPUTS_DIR`
* `DATA_DIR`
* `CHARTS_DIR`

Utility function:

* `ensure_output_dirs()`
  Creates the required output and directories if they do not already exist.

---

## Environment Variables

The module reads the following environment variables from a `.env` file at project root:

```
GITHUB_TOKEN
LOG_LEVEL
LOG_MODULES
```

`GITHUB_TOKEN` is optional but recommended for higher GitHub API rate limits.

`LOG_LEVEL` is optional and controls the verbosity used by `setup_logging()`.
Examples: `DEBUG`, `INFO`, `WARNING`, or an integer level such as `20`.

`LOG_MODULES` is optional and accepts a comma-separated list of module prefixes.
When set, `setup_logging()` keeps warnings and errors from any logger visible,
while focusing info/debug output on the selected modules.

Example:

```bash
LOG_LEVEL=DEBUG
LOG_MODULES=hiero_analytics.data_sources.github_ingest,hiero_analytics.data_sources.github_client
```

---

## Design Principles

The configuration module follows three principles:

* **Centralization** – shared constants live in one location
* **Consistency** – styling and paths remain uniform across modules
* **Separation of concerns** – configuration is isolated from business logic

---
