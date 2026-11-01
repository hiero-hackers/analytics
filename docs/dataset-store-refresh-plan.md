# Dataset store: self-heal, per-repo state, and fetch salvage

Status: proposed for #623, 2026-11-01. Sections 3.A (PR 1) and 3.B (PR 2, which also
carries most of 3.C) are implemented on `fix/623-dataset-store-self-heal`; the rest is
the plan for the PRs that follow. Kept as the design record, like `fetch-hardening-plan.md`.

## 1. What is wrong

#623 has the evidence. In short:

1. **The 30-day self-heal keys off the wrong clock.** `fetch_incremental` compares the
   *content* watermark (newest record) with `full_refresh_after`. An active dataset
   always has a fresh record, so it never full-refreshes. A quiet one full-fetches
   every night. Rows a delta cannot see (deleted, transferred, unlinked) live forever.
2. **One org-wide `since` for every repo.** A repo that joins the org, or becomes
   visible, after the watermark is only ever fetched from that watermark on.
3. **A cold fetch of a large org is fragile.** A GraphQL error in the response body
   (`RESOURCE_LIMITS_EXCEEDED`) raises from the client before the batch code sees the
   aliases that succeeded. The chunk's whole accumulation is thrown away, the width is
   fixed, and the fallback restarts from page 1.

Fixing 1 sends every dataset through 3 within 30 days; fixing 2 by bumping
`DATASET_VERSION` sends every dataset through 3 in one night. So 3 ships first.

## 2. Goals and non-goals

Goals, in shipping order:

1. A resource error or a 502 costs at most the affected alias's current page.
2. Per-repo watermarks, with backfill for repos that have none, and retirement for
   repos that have left, migrated without a one-night cold fetch.
3. Every repo full-refreshes at least every N days, staggered so that no night carries
   more than a bounded share.
4. A schema change invalidates one resource, not all of them.
5. A held watermark is visible, and a hold that persists fails the run.

Non-goals: query cost reductions (smaller `first:` on deltas, skipping repos with
`pushedAt < since`), and resuming a cold fetch *across* runs from a stored cursor
(3.B explains why a partial first fetch is persisted instead).

## 3. Design

### A. Salvage partial errors, adapt the batch width, guard pagination (PR 1)

**Typed body errors.** `RateLimitPolicy.check_graphql_errors` raises
`GraphQLResponseError(RuntimeError)` instead of a bare `RuntimeError`. It carries the
parsed response, so `data` for the aliases that succeeded is not lost. The message
stays `GitHub GraphQL error: {data}`, so `fetch_org_login`'s `NOT_FOUND` match and every
`except RuntimeError` keep working. `is_resource_limit_error(error)` classifies
`RESOURCE_LIMITS_EXCEEDED` and `MAX_NODE_LIMIT_EXCEEDED`, plus the untyped "may be
the result of a timeout" body. These errors go away with a smaller query, so they
shrink instead of failing.

Recorded shapes the fakes are built from (GitHub community reports and the
2025-09-01 resource-limits changelog, which says such queries "may return partial
results with errors"):

```json
{"data": {"r0": {"issues": {...}}, "r3": null},
 "errors": [{"type": "RESOURCE_LIMITS_EXCEEDED", "path": ["r3", "issues"],
             "locations": [{"line": 8, "column": 5}],
             "message": "Resource limits for this query exceeded."}]}
```

```json
{"data": {"r2": null},
 "errors": [{"type": "NOT_FOUND", "path": ["r2"],
             "message": "Could not resolve to a Repository with the name 'org/x'."}]}
```

`MAX_NODE_LIMIT_EXCEEDED` has no `path` and no `data`: the query was rejected before it
ran.

**A work queue instead of fixed chunks.** `fetch_repos_batched` used to cut the repo
list into fixed chunks of `GITHUB_GRAPHQL_BATCH_SIZE` and page each chunk to
completion. A chunk holding one large repo then ran a hundred single-alias rounds while
the other repos waited, and any exception dropped the whole chunk. Now the repos form
a queue. Each round carries up to `width` active aliases, and a repo that completes
frees its slot for the next one. Each repo's progress (cursor, records, pages, cursors
seen) lives in a `_RepoProgress` that outlives any single round.

**Per-alias outcome of a round.** `errors[].path[0]` names the alias an error belongs
to:

| Round outcome | Clean aliases | Affected aliases |
|---|---|---|
| success | advance | n/a |
| `GraphQLResponseError`, resource class, on some aliases | kept and advanced | page size and width shrink; retried from the unchanged cursor |
| `GraphQLResponseError`, other type (`NOT_FOUND`, `FORBIDDEN`) on an alias | kept and advanced | that repo fails |
| `GraphQLResponseError` with no alias path (`MAX_NODE_LIMIT_EXCEEDED`) | none: the round did not run | every alias in the round, as resource class |
| `GitHubServerError` (502/504 after transport retries) | none | shrink page size, then width; retry from the same cursors |
| any other exception | none | the round's repos fail; the queue continues |

"Shrink" halves the page size and the width together, through the same
`PageSizePolicy` arithmetic (each recovers after three clean rounds). Only when both
are at their floors (`GITHUB_GRAPHQL_MIN_PAGE_SIZE`, width 1) does the affected repo
fail.

**Failure keeps progress.** A repo that fails after it has fetched pages is retried
once, alone, at the end of the queue, *from its last good cursor*. If that retry also
fails, the repo is reported incomplete with the records it did fetch. Only a repo that
never fetched a page is handed to the module's per-repo fallback, whose restart from
page 1 then costs nothing. So:

- `fetch_org_records_batched` raises `PartialOrgFetchError` with every record that
  arrived, including incomplete repos' pages, and names those repos as failed. The
  store merges and holds the watermark as today.
- `fetch_repos_batched` (used directly by releases) returns records only for repos it
  completed. A failed repo's pages are dropped because the releases fallback refetches
  it from page 1. This also fixes a latent bug: those pages were saved as the repo's
  complete cache slice and then read back by the fallback.

**Pagination guards.**

- A batched alias with `hasNextPage: true` and a null `endCursor` used to be treated as
  complete (`batched.py:177`). It is now a stall, like a repeating cursor.
- Both paths remember every cursor they have seen, so a cycle (A, B, A) is caught, not
  just an immediate repeat.
- Both paths have a hard page cap, `GITHUB_GRAPHQL_MAX_PAGES` (default 5,000: 50,000
  nodes at the floor page size). Exceeding it raises `PaginationLimitError` instead of
  returning a truncated list. `paginate_cursor`'s `max_pages` keeps its documented
  soft-truncation meaning for the review pages that pass it.

### B. Per-repo state and migration (PR 2)

**Where it lives: inside each dataset file.** The file gains a `repos` map after
`records`, written by the same atomic `replace`:

```json
{"version": 2, "fetched_at": "...", "fetched_through": "...",
 "records": [...],
 "repos": {"hiero-ledger/solo": {"watermark": "...", "last_full_at": "...",
                                 "holds": 0, "missing_runs": 0}}}
```

The key is additive, so `DATASET_VERSION` stays at 2, the precedent `save_dataset` set
for `fetched_at`. Older code ignores the key and rewrites the file without it, so a
rollback costs nothing. A file without the key is seeded in place (below), so the
switch costs no cold fetch.

Rejected alternatives:

- **A separate manifest (JSON, SQLite or DuckDB).** Records and watermarks have to move
  together. With two files, a crash or a cache save between the two writes leaves a
  watermark ahead of its records, which is silent data loss. One file and one `replace`
  makes that impossible. The state is small (a few hundred repos), so a database buys
  nothing, and DuckDB would be a new dependency.
- **Stamps first, then `repos`, then `records`.** `_is_dataset_file` requires `"records"`
  in the first 256 bytes, so a large `repos` map ahead of it would hide the file from
  the prune.
- **A version bump to 3.** It would invalidate every dataset at once, which is the
  cold fetch this work exists to avoid.

`OrgIncrementalResource` gains `repo_of` (defaulting to `record.repo`, which every
incremental record has). The engine is `dataset_store.fetch_incremental_by_repo`, and
`fetch_org_incremental` lists the org once and calls it. Each run plans each listed
repo:

| Repo state | Fetch |
|---|---|
| no entry, or no watermark (new, late-joining, or a first fetch that failed) | full fetch of that repo (backfill) |
| `last_full_at` older than `full_refresh_after` (30 days), or `--refresh` | full fetch of that repo |
| otherwise | delta from that repo's own watermark |

**What a repo's watermark means.** It is the dataset's content watermark (the newest
`updated_at` in the dataset) as of the last run in which that repo's fetch completed.
That is the value today's org-wide watermark has, so deltas see exactly what they saw
before. Repos that complete together share it, so a night's delta is still one batched
fetch. A held repo keeps its older value and gets a second, small delta group.
Per-repo *content* watermarks were rejected: every quiet repo would get its own
`since`, breaking batching into one request per repo.

- A repo's full fetch that completes *replaces* that repo's rows. That is where
  deleted and transferred records go.
- A partial full fetch *merges*, and `last_full_at` does not move, so the refresh is
  retried the next night.
- A delta merges, and advances only the watermarks of the repos it completed.
- The dataset-level `fetched_through` is the oldest listed repo's watermark, which is
  what it always meant. `fetched_at` keeps its prior value on any run that held a
  repo, as a held watermark always did.

**Partial first fetch.** Today a first fetch that loses one repo persists nothing,
which is how the 14 Oct run threw away 23 good repos. Now the repos that completed are
saved with watermarks, and the failed ones are saved without one, so they are fetched
in full the next night. Only a first fetch in which *nothing* completed re-raises. With
no prior freshness stamp to keep, such a file claims its own content watermark as
`fetched_at`, never "now".

Resuming the failed repos from a stored cursor the next night is rejected: cursors on
`UPDATED_AT`-ordered connections drift, so a resumed fetch could skip records with no
signal. A fresh full fetch of the failed repos is correct, and 3.A makes it cheap to
retry.

**Retiring a repo that left the org.** The listing can come from the 14-day TTL cache,
and a single listing call can miss a repo. Rows are retired only when all of these
hold:

1. the repo has been absent from the listing on 2 or more consecutive runs
   (`missing_runs`);
2. a direct `repository(owner, name)` lookup (`_common.repository_is_gone`, one point)
   confirms it: `NOT_FOUND`, or a different `nameWithOwner`, meaning GitHub resolved a
   rename or transfer. A failed lookup is not evidence.
3. no more than 20% of the dataset's repos are missing at once (at least one may always
   retire). A revoked token or an empty listing must not retire everything.

Until then the repo's rows stay and it is simply not fetched. Retirement is logged at
WARNING; listing it in `SNAPSHOT.json` is part of 3.E. A rename is handled correctly as
a side effect: the new name is backfilled the night it appears, and the old name's rows
retire two runs later, so nothing is counted twice.

**Migration (a file without `repos`).** Nothing is discarded, so nothing is
cold-fetched:

- each repo with records gets `watermark` = the file's `fetched_through`, and a
  *seeded* `last_full_at` (3.C), so its first full refresh lands somewhere in the next
  30 days, not tonight;
- repos with no records get no entry, so they are fetched in full tonight. That is
  cheap by construction, and it backfills repos the old org-wide `since` never covered.
- Repos with records that are no longer listed (rows that have outlived their repo)
  are seeded too, so they enter the retirement rules. **This will lower some all-time
  totals on first deploy**, by design.

`solo-charts` (47 records) gets an entry and is corrected by its seeded full refresh
within 30 days.

Tests:

- `test_dataset_store_per_repo.py` covers planning, holds, partial first fetches,
  replace-on-refresh, migration, corrupt state, offline runs and every retirement rule.
- `test_refresh_simulation.py` runs 60 nights of a fake org through the real
  `fetch_org_issues_graphql`, batched engine and store, and covers #623's (a) to (d)
  plus a retirement.

**Dry run against production data** (2026-11-01, nightly run 41259245903 at
`36655bb`, all three orgs, 13 per-repo datasets, about 460,000 rows). Read-only: the
snapshot was seeded into a scratch directory, and each org was listed without the
cache.

- **Every dataset migrates in place.** Each one loads and seeds, so no cold fetch
  happens on deploy night.
- **Backfills on deploy night** are listed repos with no rows in that dataset: 2 to 5
  per hiero-ledger dataset (for example `hiero-identity-standards`,
  `solo-build-actions`), 6 to 17 for hiero-hackers, 0 to 4 for LFDT-CLPR.
- **Retirements: two repos.** `hiero-hackers/clpr-evm-endpoint` and
  `hiero-hackers/clpr-smart-contracts` were transferred to LFDT-CLPR. The lookup
  confirms both are gone, so their 2 merged-PR rows and 7 contributor-activity rows
  leave hiero-hackers' totals. No rows are filed under another owner.
- **`solo-charts`** has 47 label-event rows, the figure in #623. Its seeded first full
  refresh falls on night 15.
- **Scheduled refreshes by repo count:** at most 4 per night per dataset, about 1.4 on
  average.
- **By size, the nights are uneven.** Repos differ by orders of magnitude, so one
  night refreshes 40% of `contributor_activity`'s rows (`hiero-consensus-node`,
  `heka-identity-platform`, `hiero-sdk-python` and `solo-containers` together), and
  another 29% of `issue_label_events`.
- **Estimated extra cost.** Points per repo page come from that night's own
  `api_usage` (1,000 points in total). Each due repo adds about (pages - 1) of them:
  about 160 points a night on average, about 5,000 across the window (about one full
  fetch of everything, as expected), and 600 to 670 on the three worst nights. That is
  well within a 5,000-points-an-hour PAT, but lumpy. 3.C weights the stagger by size.

### C. Staggered `last_full_at` self-heal (PR 3)

The per-repo gate (`now - last_full_at >= full_refresh_after`) and the stagger shipped
with 3.B, because the migration's seeding *is* the stagger:

- A seeded `last_full_at` is `now - N * (1 - f)`, where `f` comes from
  `sha256(dataset file, repo)` in `[0, 1)`. The repo comes due `N * f` days later:
  spread uniformly, staggered across resources and orgs, and deterministic.
- A repo's *first* full fetch (a cold fetch, or a backfill) gets the same seeded stamp,
  not "now". Otherwise a cold fetch of a whole org would come due again all on one
  night 30 days later. This costs at most one early refresh per repo, once.
- After that, each repo comes due N days after its own last refresh.

Measured in the tests: 40 migrated repos, at most 4 full refreshes on any night of the
first window, each repo exactly once. 60 cold-fetched repos, at most 6 a night. In the
60-night simulation, at most 2 a night.

What remains for PR 3:

- **Size-aware seeding.** The dry run shows a hash spreads repos evenly but not
  *work*: a night that draws two of the largest repos carries 40% of a dataset. Seed
  instead by greedy assignment, largest repo first, to the night with the least
  estimated pages so far (deterministic, still per resource and org). Everything after
  the first window keeps that spacing. `hiero-consensus-node` alone is 25 to 30% of
  some datasets, a floor no schedule can go below without splitting one repo's refresh
  across nights.
- **A nightly budget**: at most `ceil(2 * repos / N)` scheduled refreshes per
  (resource, org), most overdue first. Backfills are not budgeted, because they are the
  only way to get the data. This is the backstop for missed nights (a cache eviction,
  a skipped save), which would otherwise bunch the overdue repos.
- **Single-file datasets**: `fetch_incremental`'s own `full_refresh_after` (the HIP
  inventory, `hip_references.py:226`) still gates on the content watermark. It switches
  to a stored dataset-level `last_full_at`, which fixes the quiet-dataset-every-night
  case.
- **The budget figures** in `docs/api-budget.md`, from the rehearsal.

### D. Per-resource schema versions (PR 4)

`version` stays the *file format* (still 2: 3.B was additive). Each resource declares
`schema_version` on `OrgIncrementalResource`, defaulting to 1, and on the `load_or_fetch`
callers. The file stores `"schema"`, and a mismatch invalidates that resource only.
A file without `"schema"` maps to schema 1 for every resource, since the global v2
bump already covered `issue_label_events`.

### E. Held watermarks, health gate, plausibility (PR 5)

- **Recording.** `fetch_incremental` records each dataset's outcome (held repos,
  consecutive holds, full-refreshed repos, retired repos, records added and removed)
  in a per-process registry, like `touched_datasets`. `write_snapshot_manifest` adds
  it to `SNAPSHOT.json`, and the job summary gets a "Held watermarks" table.
- **Failing loudly without losing data.** If the pipeline step failed on a hold, CI
  would skip `Save incremental datasets` and throw away the night's progress, which
  is the loop this issue is about. So the pipeline step stays green on holds. A
  separate `dataset-health` job after `refresh-data` reads the archived `SNAPSHOT.json`
  and fails when any repo has 3 or more consecutive holds (configurable). The data is
  saved, the dashboard deploys, and the run is red.
- **Plausibility.** The gate also fails when:
  - a dataset shrinks by more than 5% in a run that neither full-refreshed nor retired
    the repos that lost rows. A delta merge cannot remove rows, so this means
    corruption.
  - a repo's `last_full_at` is older than `full_refresh_after` + 7 days. That is the
    invariant the self-heal guarantees, and the direct form of "grew monotonically for
    30 runs".

  Monotonic growth itself is shown as a warning, not a failure. Event datasets
  (`contributor_activity`, `issue_label_events`) are append-only, and a healthy
  `issues` dataset grows on net through any night with more new issues than
  deletions. As a failing check it would cry wolf.

## 4. Rollout

| PR | Change | Needs | Verify | Rollback |
|---|---|---|---|---|
| 1 | 3.A | #621 (merged) | fakes for each recorded shape; a forced cold run of `issue_label_events` for hiero-ledger, reporting points from `SNAPSHOT.json` `api_usage` | revert; no data format change |
| 2 | 3.B, and 3.C's gate and stagger | 1 | migration in place; planner dry run on the nightly snapshot; 60-night simulation, (a) to (d) | revert; the `repos` key is additive, so older code ignores it |
| 3 | rest of 3.C | 2 | a missed-nights simulation stays within the budget; the HIP inventory stops refreshing nightly | revert; the schedule is data, nothing to undo |
| 4 | 3.D | 2 | bump one resource's schema in a test; the others load | revert |
| 5 | 3.E | 3 | a simulated 3-night hold fails the gate after save; a shrink fixture fails it | revert the job |

The multi-night simulation is one test module driving the real
`fetch_org_batched_incremental` (planner, batched engine, store) against a fake GitHub
org with a clock. Nights inject a deletion, a transfer, a late-joining repo, a
`RESOURCE_LIMITS_EXCEEDED` round and a 502. It grows with each PR, and covers
#623's (a) to (d).

## 5. Decisions for the maintainer

1. **N.** 30 days, as today's `full_refresh_after`; budget multiplier 2.
2. **Hold threshold for the gate.** 3 consecutive runs.
3. **Monotonic growth as a warning, not a failure** (3.E). This deviates from #623's
   literal ask, for the reason given there.
4. **`GITHUB_GRAPHQL_MAX_PAGES` = 5,000.** A guess with headroom, not a measurement.
   The largest connection seen is `solo` PRs at about 115 pages of 100.
