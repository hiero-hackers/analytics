# GitHub API budget

What a refresh costs in GitHub API budget, what adding an organisation adds, and
why the refresh cadence is what it is. Every run reports its own spend, so this
document is meant to be kept honest with that data rather than with estimates.

## Where the numbers come from

Every request is attributed to the **organisation** and **dataset** (or pipeline,
for requests outside a persisted dataset) it was made for. The data
(`src/hiero_analytics/data_sources/usage.py`) is reported in two places, from the
same figures:

- the `api_usage` block of `SNAPSHOT.json` (archived with every snapshot), and
- the **GitHub API usage** table in the Actions job summary for the run.

Per organisation and dataset it records REST requests, GraphQL requests, and
GraphQL points spent; per run it also records the `rateLimit.remaining` GitHub
last reported.

Counting rules, so the numbers are read correctly:

- A request is counted **per HTTP response received**, so a retried request counts
  each attempt. A request that never got a response (connection error, timeout)
  is not counted.
- GraphQL points come from the `rateLimit.cost` GitHub returns, not an estimate.
- `graphql_remaining` is the *last* value observed. With concurrent workers
  "last" is approximate: use it as a gauge of how close a run came to the limit,
  not as an exact figure.
- Requests made outside any scope appear under `unattributed`. A large
  `unattributed` row means some fetch path is not scoped; it is a prompt to fix
  the scoping, not noise to ignore.

## The budget model

Two tokens can run the refresh, and they have different limits:

| Token | GraphQL budget | Notes |
| --- | --- | --- |
| `ANALYTICS_PAT` (classic PAT) | 5,000 points / hour | Used when the secret is configured. |
| Actions `GITHUB_TOKEN` | 1,000 points / hour per repository | Fallback, so forks keep working. |

(Limits as documented in the workflow comments; GitHub can change them.)

The client does not fail when the budget runs out: it sleeps until the window
resets and carries on. Budget therefore shows up as **wall time**, not errors,
which is why the workflow's job timeout is generous. Concurrency is capped by
`GITHUB_MAX_WORKERS` (3 in CI, 6 by default) to avoid secondary rate limits.

How much of that budget a run spends depends on what it has to fetch. A dataset
file on disk moves through three regimes:

| Watermark age | What happens | Relative cost |
| --- | --- | --- |
| under 5 days (`DEFAULT_REUSE_MAX_AGE`) | reused as-is, no fetch | none |
| 5 – 30 days | incremental: only records updated since the watermark | small |
| over 30 days (`full_refresh_after`), or no dataset | full fetch / rebuild | large |

The incremental cache is restored between runs by `actions/cache`. If it is
evicted, the next run does one full fetch and then resumes incrementally.

This is why the cost of an organisation has two very different parts, and why
they are reported separately below.

## Measured cost

> **Status: not yet measured.** The figures below must come from real runs
> against the production token, because they depend on the size of the
> organisations and on rate-limit sleeps that cannot be reproduced offline.
> Nothing in this section is an estimate; empty cells are empty on purpose.

How to fill it in: run the *Refresh Analytics Data* workflow (or
`uv run hiero-analytics` with a token) and read the **GitHub API usage** table
in the job summary, or `api_usage` in the run's `SNAPSHOT.json`.

**Steady state** (a normal scheduled run on a warm cache):

| Organisation | REST requests | GraphQL requests | GraphQL points | Wall time |
| --- | --- | --- | --- | --- |
| _(primary org)_ |  |  |  |  |
| _(each extra org)_ |  |  |  |  |

Record several consecutive runs rather than one, and note the date and the
token used.

**Cold start** (first fetch of an org, or a run after cache eviction), recorded
separately because it is a one-off cost and is the part that decides whether the
Actions token can run it at all:

| Organisation | GraphQL points | Hours of budget (points ÷ token limit) | Wall time |
| --- | --- | --- | --- |
| _(measured on an org added to an empty cache)_ |  |  |  |

## Forecast: adding one more organisation

Adding an org to `GITHUB_EXTRA_ORGS` adds two costs, and they must not be
summed into one number:

1. **A one-off cold fetch** — the full-fetch GraphQL points for that org, taken
   from the cold-start table. Divide by the token's hourly limit to get the
   hours of budget it consumes; with the Actions token this can exceed the job
   timeout, which is the case for configuring `ANALYTICS_PAT` first.
2. **A recurring steady-state cost per run** — the incremental points for that
   org, taken from the steady-state table, multiplied by the runs per month
   (about 6 at the current 5-day cadence).

Only the second cost is relevant to the question "does the schedule still fit?".
The first is relevant to "can this token and timeout survive onboarding?".

A rough size guide is to scale the nearest measured org by its repository count,
but the measured numbers above supersede it as soon as they exist.

## Cadence decision

**Current: refresh every 5 days (`cron: '0 9 */5 * *'`) with a 5-day reuse
window (`DEFAULT_REUSE_MAX_AGE`).** These two values are one decision and must
change together: the reuse window should not be shorter than the interval
between runs (every run would then refetch), nor so much longer that data is
served stale.

**Recommendation: no change until the measurements above exist.** The cadence
was chosen to keep gaps under the 7-day cache-eviction window; nothing in the
usage data collected so far argues for moving it, and changing it without
measurements would be guessing. When the tables are filled in, revisit as
follows:

- If steady-state points per run are a small fraction of one hour's budget for
  the token in use, the schedule has headroom and the cadence can stay or
  shorten.
- If steady-state points approach the hourly budget (so runs are dominated by
  rate-limit sleeps), lengthen the cron interval and `DEFAULT_REUSE_MAX_AGE`
  together, keeping gaps under the cache-eviction window.
- If cold-start hours exceed the job timeout for the token in use, fix the token
  (PAT) rather than the cadence.

Record the decision and the measured figures that support it here, with the
date, whenever it changes.
