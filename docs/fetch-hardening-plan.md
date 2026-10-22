# Fetch hardening: plan and migration

Status: implemented on the LFDT-CLPR branch, 2026-10-15 (sections 3.A to 3.D in one commit; phase 0 is manual). Kept as the design record.

## 1. What the 15 October local run exposed

A full local run (`uv run hiero-analytics`) on the CLPR branch took 26 minutes, failed
one pipeline, and did not render the org it was meant to add. None of it was a pipeline
bug; all of it was avoidable.

| Symptom | Cause | Where |
|---|---|---|
| CLPR not rendered, with no explanation until the data API step | `GITHUB_EXTRA_ORGS=hiero-hackers` in `.env` is an allow-list over the registry's extras, so a registered org is silently left out | `config/orgs.py` `extra_orgs()` |
| `contributor_activity` failed for hiero-ledger after 20 minutes of 502s | No local `merged_pr_difficulty_hiero-ledger_all.json`, so the GFI tile did a cold fetch of about 27,000 merged PRs; GitHub GraphQL 502s on the largest repo (`solo`, 11,500 PRs) at the fixed page size of 100, and three identical retries cannot help | `data_sources/pagination.py` `DEFAULT_PAGE_SIZE`, `github_client.py` `RETRY_STATUS_CODES` loop, `queries/*.graphql` `first:100` |
| A follow-up single-org run (`GITHUB_ORG=LFDT-CLPR`) deleted the hiero-ledger and hiero-hackers datasets | The end-of-run prune treats any dataset no resource claimed as an orphan, and a narrowed run claims only its own orgs' datasets. The behaviour is documented in the prune's docstring; it is still a trap | `dataset_store.py` `prune_untouched_datasets`, `pipelines/run_all.py` prune call |
| The first local run is hours, and fails if GitHub is flaky that day | Nothing seeds a fresh clone from the nightly run's datasets, although CI archives them as an 8 MB artifact every night | `.github/workflows/update-analytics.yml` "Archive dataset snapshot" |

What worked, and must keep working: the partial-fetch contract (watermark held, failure
isolated, run completed), the CI cache (CI never did the cold fetch), the capability
scheduling for the new org.

## 2. Goals and non-goals

Goals, in priority order:

1. A narrowed local run never destroys cache for an org that is still registered.
2. A cold fetch of a large repo survives GitHub's GraphQL 502s without human help.
3. The run says, up front, when the environment is hiding a registered org.
4. A fresh clone can reach a warm cache in about a minute.

Non-goals here: query-level efficiency (fewer points per fetch), resumable cold fetches
across runs, and reporting usage per org. Those remain separate issues; this plan only
makes the current fetch robust and the local workflow safe.

## 3. Design

### A. Scope the prune to the orgs this run could judge

Current rule (`run_all.main`): after a clean online run, delete every dataset file nothing
claimed, keeping only datasets of orgs whose pipelines failed. "Registered but not
rendered because the environment narrowed the run" is indistinguishable from "removed
from the registry".

New rule: a dataset is an orphan only when its org is neither rendered this run nor
registered. Concretely, the `keep` predicate becomes

```python
unjudged = failed_orgs(failures) | (set(org_registry.org_names()) - set(orgs))
prune_untouched_datasets(keep=_belongs_to_any(unjudged))
```

`_belongs_to_any` already matches by the `_<org>_` slug in the file name, so no file
format change. Behaviour matrix:

| Dataset's org is... | Today | After |
|---|---|---|
| rendered, claimed | kept | kept |
| rendered, not claimed (fetch renamed or re-scoped) | pruned | pruned |
| registered, excluded by `GITHUB_ORG` / `GITHUB_EXTRA_ORGS` | **pruned** | **kept** |
| a past trial org, not rendered now | pruned | pruned |
| removed from the registry | pruned | pruned |

Files: `pipelines/run_all.py` (two lines), `dataset_store.py` docstring paragraph that
documents the old trap, `docs/adding-an-organisation.md` "Removing an organisation" stays
true. Tests: one new case in `tests/pipelines/test_run_all.py` beside
`test_main_prunes_but_keeps_a_failed_extra_orgs_datasets`, parametrised over narrowing
by `GITHUB_EXTRA_ORGS` and by `GITHUB_ORG`; the existing registry-removal and trial-org
cases must stay green.

Risk: none for CI, which always renders the whole registry. The only behaviour change is
on narrowed runs, which are local by construction.

### B. Name the registered orgs the environment leaves out

`extra_orgs()` already warns about names in `GITHUB_EXTRA_ORGS` that are not registered.
Add the inverse, once per run, in `run_all.main` right after the "Rendering N org(s)"
line (not inside `extra_orgs()`, which is called from several modules and would repeat):

```
Rendering 2 org(s): hiero-ledger, hiero-hackers
Environment leaves out registered org(s): LFDT-CLPR (GITHUB_EXTRA_ORGS is set; unset it to render the registry)
```

INFO level, since narrowing is legitimate for development. Files: `pipelines/run_all.py`.
Test: `caplog` assertion in `test_run_all.py`.

### C. Adaptive page size on GraphQL server errors

GitHub answers a GraphQL query that runs too long with 502 (or 504). Retrying the same
page is futile; asking for fewer nodes is the documented remedy. Today the page size is
baked into the query text (`first:100` in eight `.graphql` files) and the transport
retries three times with 2, 4, 8 second backoff, then raises `requests.HTTPError`.

Design, in four layers so each is testable alone:

1. **Queries take the page size as a variable.** Replace `first:100` with
   `first:$pageSize` and declare `$pageSize: Int!` in each query header. The batched
   builder's `split_repo_query` already classifies declarations: anything not
   `$owner/$repo/$cursor` is shared across the round, which is exactly what a round-wide
   page size should be. Nested `reviews(first:100)` inside
   `contributor_activity.graphql` stays literal; it is not the paginated edge.
2. **The transport raises a typed error.** After exhausting its 5xx retries,
   `_RestTransport.request` raises `GitHubServerError(requests.HTTPError)` carrying the
   status. Subclassing keeps every existing `except HTTPError` and the broad
   `except Exception` in `fetch_all_with_retry` working unchanged.
3. **The pagination loop shrinks and remembers.** `paginate_cursor(fetch_page, ...)`
   gains `page_size=DEFAULT_PAGE_SIZE` and `min_page_size=10`, and `fetch_page` takes
   `(cursor, page_size)`. On `GitHubServerError` it halves the size and retries the same
   cursor; at the floor it re-raises. The reduced size persists for the rest of that
   resource (the repo that was slow stays slow), with an optional doubling back after
   three clean pages so a transient blip does not pin a repo at 12 nodes a page.
   `fetch_github_resource.page` passes `pageSize` into the variables.
4. **Batched rounds do the same.** `_fetch_chunk` wraps `client.graphql` in the same
   shrink loop with a round-level `pageSize`; all aliases in the round shrink together,
   which is correct because the round's cost is their sum.

Budget: GraphQL points are charged per node, so smaller pages cost the same points and
only add round trips, and only on the failure path. Fingerprints and TTL cache keys are
built from explicit `cache_parameters`, not from the variables dict, so adding
`pageSize` invalidates nothing on disk or in CI's cache.

Files: `queries/*.graphql` (8), `data_sources/queries.py` (no change expected),
`github_client.py` (typed error), `pagination.py`, `github_ingest/_common.py`,
`github_ingest/batched.py`, `docs/api-budget.md` (one paragraph). Tests:
`test_pagination.py` (halving, floor, persistence, recovery), `test_batched.py`
(round-level shrink, aliases keep their cursors), `test_github_client.py` (typed
error), and a query-text test asserting every paginated query declares `$pageSize` and
no `first:100` remains on a cursor edge.

Risk: the query edit touches every fetch. Mitigation is the existing `split_repo_query`
tests plus the new query-text test, and a verification cold fetch (section 4).

### D. Seed a local cache from the nightly artifact

Add `hiero-analytics seed-datasets [--repo OWNER/NAME] [--run-id N] [--force]`:

1. Find the latest `update-analytics.yml` run with `conclusion == success` on the
   default branch (the artifact is uploaded `if: always()`, so a failed run's partial
   snapshot must be skipped unless `--run-id` names it explicitly).
2. Download its `dataset-snapshot-<run>-<sha>` artifact with the user's `GITHUB_TOKEN`
   (artifact downloads need authentication even on public repos).
3. Validate before writing: zip entries are flat `*.json` basenames only (no paths),
   each parses and carries the `version` key the dataset store writes, and
   `SNAPSHOT.json` is present; total size under a sane cap.
4. Write into `outputs/data/datasets/`. Refuse to overwrite a non-empty directory
   without `--force`; print the snapshot's run id, code revision and `data_as_of` so the
   developer knows what they now have.

The README's "the first run is slow" paragraph points at the command; CONTRIBUTING's
setup section gets one line. Forks pass `--repo`. Files: `cli.py`, a new
`data_sources/dataset_seed.py` (HTTP via the existing `GitHubClient`, so rate-limit
handling and headers are shared), tests with a fake zip. Scorecard note: the command
only ever downloads from the configured repository's own Actions artifacts.

## 4. Migration and rollout

| Phase | Change | Branch / PR | Needs | Verify | Rollback |
|---|---|---|---|---|---|
| 0, today | Restore the deleted local cache from run 38664372333's artifact; remove `GITHUB_EXTRA_ORGS` from `.env` | none | `gh` + maintainer approval for the download | `uv run hiero-analytics` renders 3 orgs in about 15 min | n/a |
| 1 | A + B | one small PR from `main` | nothing | new tests; a deliberate narrowed run (`GITHUB_EXTRA_ORGS=""`) leaves the other orgs' datasets in place and logs the exclusion | revert; no data migration |
| 2 | D | one PR from `main`, independent of 1 | the Actions artifact (already produced nightly) | fresh clone, `seed-datasets`, then a full run completes offline-fast | revert; the command is additive |
| 3 | C | one PR from `main`, after 1 (so the verification cold fetch cannot wipe a cache) | nothing in CI | see below | revert the PR; the query variable and the shrink loop ship together so there is no half state |
| 4, optional | `--log-file` for local runs; the `GFI completers` tile's org-wide merged-PR fetch is the single most expensive dataset, revisit in the efficiency issue | later | | | |

Verification for phase 3, on a machine with a seeded cache: delete only
`merged_pr_difficulty_hiero-ledger_all.json`, run `GITHUB_EXTRA_ORGS="" uv run
hiero-analytics contributor_activity`, and watch `solo` page at 100, drop to 50 or 25 on
the first 502, and finish; then confirm the next incremental run is unchanged. Phase 1
must land first, or this experiment prunes the other orgs' datasets (today's accident).

CI implications: none of A to D changes what the scheduled workflow fetches or caches.
A changes nothing in CI because CI renders the whole registry; C only activates on 5xx,
which CI also sees on cold fetches of new orgs, so it makes the first run of a new org
more likely to succeed within the job timeout. The trial-org path and the preview
workflow are unaffected.

Order of merging is 1, 2, 3; 2 and 3 can be developed in parallel.

## 5. Issue breakdown (superseded: shipped together on the CLPR branch)

| Issue | Scope | Level | Size |
|---|---|---|---|
| Keep a registered org's datasets when a run is narrowed, and say which orgs the environment leaves out | A + B | beginner | ~4 h |
| Seed the local dataset cache from the nightly snapshot artifact | D | intermediate | ~1 day |
| Shrink the GraphQL page size on 502 instead of retrying the same page | C | intermediate | ~2 days |

Each issue should link this document and name its phase.

## 6. Decisions for the maintainer

1. Floor and recovery for C: 10 nodes and double back after three clean pages are
   proposals, not measurements. Keep them as module constants with env overrides, like
   `GITHUB_GRAPHQL_BATCH_SIZE`.
2. Whether `seed-datasets` should also be the documented first step for every contributor
   (README quickstart), or stay an optional accelerator. Recommendation: first step, since
   a cold fetch now takes longer than a test run of the whole suite.
3. Whether a narrowed run should log at INFO or WARNING. Recommendation: INFO; it is a
   normal development mode.
