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

How much of that budget a run spends depends on how each dataset is fetched.
Datasets follow one of two paths:

| Path | Datasets (examples) | Behaviour on an existing dataset |
| --- | --- | --- |
| Reused (`load_or_fetch`) | `contributor_activity`, `ci_health`, `onboarding`, the REST `codeowner_and_runner` data | Reused with **no fetch** by a run's later pipelines while the last fetch is under 6 hours old (`DEFAULT_REUSE_MAX_AGE`, measured from `fetched_at`); every new run refetches. |
| Incremental (`fetch_incremental`) | `issues`, `issue_label_events`, `merged_pr_difficulty`, `releases`, `pr_hip_references` | Fetches records updated since the watermark **on every run**, regardless of age; a full refetch once the watermark is over 30 days old (`full_refresh_after`). |

So a run's floor is not zero: the incremental datasets are always queried. The
reuse window only saves the datasets on the first path, and only within one run.

The dataset cache is restored between runs by `actions/cache`. If it is evicted,
the next run does one full fetch and then resumes incrementally.

This is why the cost of an organisation has two very different parts, and why
they are reported separately below.

## Measured cost

Measured on 2026-10-09 against `hiero-hackers` with a personal classic PAT
(5,000 points/hour), `GITHUB_MAX_WORKERS=3`, from a developer machine.
`GITHUB_REPO=analytics` was set: repo-level pipelines (`onboarding`,
`contributor_profiles`) default to `hiero-sdk-python` and fail on an org that has
no repository of that name, so set `GITHUB_REPO` when measuring another org.

How to reproduce: `uv run hiero-analytics` with a token, then read the **GitHub
API usage** table in the job summary (`GITHUB_STEP_SUMMARY`), or `api_usage` in
`SNAPSHOT.json`. Measure cold start from an empty `outputs/` directory.

| Run | REST requests | GraphQL requests | GraphQL points | % of one hour (PAT) | Wall time |
| --- | ---: | ---: | ---: | ---: | --- |
| Cold start (empty `outputs/`) | 165 | 217 | 525 | 10.5% | 12m 12s |
| Warm, run straight after (nothing cleared) | 0 | 42 | 292 | 5.8% | 6m 19s |

Where the points go (GraphQL points, cold / warm):

| Dataset | Cold | Warm |
| --- | ---: | ---: |
| `merged_pr_difficulty` | 192 | 168 |
| `issue_label_events` | 86 | 56 |
| `contributor_activity` | 62 | reused |
| `hiero_hackers` | 62 | reused |
| `issues` | 58 | 56 |
| `ci_health` | 28 | reused |
| `onboarding` | 20 | reused |
| `pr_hip_references` | 10 | 6 |
| `releases` | 6 | 5 |
| `hip_implementation` | 1 | 1 |
| `codeowner_and_runner` (REST) | 165 requests | reused |

Reading the table:

- The incremental datasets are most of the steady-state cost. Their warm cost
  (e.g. 168 of 192 points for `merged_pr_difficulty`) is close to their cold cost,
  so a delta fetch at this size is far from free. Why is not yet investigated.
- **Limits of this data.** The warm run came minutes after the cold run, so its
  deltas were as small as they get; a nightly run has a day to fetch and may
  cost somewhat more. It is a lower bound for steady state, not an average. It is
  also a single org and a single run of each kind, from a developer machine.

## Forecast: adding one more organisation

Adding an org to `GITHUB_EXTRA_ORGS` adds two costs, and they must not be
summed into one number:

1. **A one-off cold fetch**, for `hiero-hackers`-sized orgs about 525 GraphQL
   points plus about 165 REST requests and roughly 12 minutes. Divide by the
   token's hourly limit to get the hours of budget it consumes. Scale by
   repository and activity volume for other orgs; `hiero-ledger` is much larger
   and has **not** been measured.
2. **A recurring cost per run**, at least the warm figure (about 290 points for
   `hiero-hackers`), times runs per month (about 30 at the daily cadence), so
   about 8,700 points per month per org of this size.

Only the second matters for "does the schedule still fit?". The first matters
for "can this token and timeout survive onboarding?". The Actions
`GITHUB_TOKEN` has a lower hourly budget than a PAT (see above), so the cold
fetch of a large org is the case that needs `ANALYTICS_PAT` configured first.

## Cadence decision

**Current: refresh daily at 04:00 EAT, 01:00 UTC (`cron: '0 1 * * *'`), since
2026-10-10.** That is outside working hours for the maintainers (02:00-03:00 in
Central Europe, evening in the Americas), so a manual run
during the day has the hour's budget to itself. The reuse window
(`DEFAULT_REUSE_MAX_AGE`, 6 hours) only spans one run, so it does not have to
match the cron. `STALE_AFTER` (36 hours, `export/data_api.py`, mirrored in
`web/src/components/AppHeader.tsx`) does: it is one day plus 12 hours of slack,
so one missed night shows as stale.

Before that the refresh ran every 5 days (`cron: '0 9 */5 * *'`), so the
recent-activity windows were up to 5 days behind between runs.

Until 2026-10-10 the reuse window was 5 days, measured from the newest event
rather than the last fetch, and was meant to match the cron. It made runs skip
fetching: the dispatched run of 2026-10-09 reused the activity data of
2026-10-06, and `*/5` restarts each month, so runs 1 to 3 days apart (the 31st
then the 1st, or 26 February then 1 March) skip too. Each such run still ended
its Week, 1 month and 1 year windows at its own clock, so `hiero-ledger`'s
repository and contributor views showed days of missing activity as a quiet
week (for example, 0 issues opened in `hiero-sdk-python`'s Week against 9 on
GitHub). The change makes every run pull the contributor-activity delta, which
is cheap next to the incremental datasets.

**Budget for the daily run.** The dispatched run of 2026-10-09 (run
`37984987230`, `api_usage` in its `SNAPSHOT.json`) spent 970 GraphQL points and
760 REST requests across both orgs: 656 points and 595 requests for
`hiero-ledger`, 314 points and 165 requests for `hiero-hackers`. It reused
`contributor_activity`, which every run now fetches as a delta: about two
requests per repository, so on the order of 100 to 200 more points for
`hiero-ledger`'s 44 repositories (an estimate, not yet measured). That is about a
quarter of one hour's PAT budget, once a day, so the daily schedule has ample
headroom. Points for anyone revisiting it:

- Because incremental datasets are fetched on every run, total monthly cost
  scales roughly with the number of runs: about 30 runs a month now, against
  about 6 at the old cadence.
- Re-measure from the first nightly runs' `api_usage` and record the figures
  here; the Actions `GITHUB_TOKEN` fallback (1,000 points / hour) would not fit
  a cold fetch of `hiero-ledger` in one hour either way.

Record any change here with its supporting figures and the date.
