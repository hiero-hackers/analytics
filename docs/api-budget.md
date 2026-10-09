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
| Reused (`load_or_fetch`) | `contributor_activity`, `ci_health`, `onboarding`, the REST `codeowner_and_runner` data | Reused with **no fetch** while the watermark is under 5 days old (`DEFAULT_REUSE_MAX_AGE`); refetched once older. |
| Incremental (`fetch_incremental`) | `issues`, `issue_label_events`, `merged_pr_difficulty`, `releases`, `pr_hip_references` | Fetches records updated since the watermark **on every run**, regardless of age; a full refetch once the watermark is over 30 days old (`full_refresh_after`). |

So a run's floor is not zero: the incremental datasets are always queried. The
reuse window only saves the datasets on the first path.

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
  deltas were as small as they get; a run after 5 days has more to fetch and may
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
   `hiero-hackers`), times runs per month (about 6 at the 5-day cadence), so
   about 1,750 points per month per org of this size.

Only the second matters for "does the schedule still fit?". The first matters
for "can this token and timeout survive onboarding?". The Actions
`GITHUB_TOKEN` has a lower hourly budget than a PAT (see above), so the cold
fetch of a large org is the case that needs `ANALYTICS_PAT` configured first.

## Cadence decision

**Current: refresh every 5 days (`cron: '0 9 */5 * *'`) with a 5-day reuse
window (`DEFAULT_REUSE_MAX_AGE`).** These two values are one decision and must
change together.

**Recommendation: keep it as is.** For an org of `hiero-hackers`' size a cold
run uses about a tenth of one hour's budget and a steady run about 6%, so the
schedule has ample headroom and there is no cost reason to change it. Two
points for anyone revisiting it:

- Because incremental datasets are fetched on every run, total monthly cost
  scales roughly with the number of runs; lengthening the interval cuts cost
  proportionally, shortening it raises cost proportionally. The reuse window
  only affects the datasets on the reused path.
- This is based on one small org. The decision should be revisited with
  measurements for `hiero-ledger` and for the Actions token before the schedule
  is tightened or onboarding a large org; the follow-up issues are the place
  to track that.

Record any change here with its supporting figures and the date.
