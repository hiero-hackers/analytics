Title: feat: add the LFDT-CLPR organisation, stabilise affiliation curation, harden the fetch

**Description**:

Add LFDT-CLPR to the dashboard as a governed extra organisation, move affiliation hand corrections into their own file with a monthly refresh PR, and fix the four fetch problems the first local run of the new org exposed.

Commit 1, CLPR:

* Register `LFDT-CLPR` in `config/orgs.py` with `display_name="CLPR"`, `extra=True`
* Point `governance_url` at the org's `governance/teams.yml`, which has the same `teams` / `repositories` shape the parser reads, so CLPR gets the Governance tab
* Declare `lfdt-staff` as a blanket team: it holds maintain or admin on all five CLPR repos and would otherwise be credited as every repo's maintainers
* Add the CLPR mark under `web/public/brand/clpr/` (light and dark variants) and set `brand="clpr"`, so the header shows it while CLPR is selected
* Refresh `affiliations.yaml` from live signals with CLPR in the governed roster

Commit 2, affiliation curation (`docs/affiliations.md` has the full story):

* Split curated from generated: `affiliations.yaml` is pure resolver output with a GENERATED header; every hand correction is a `login: "Organisation"  # reason` row in the new `affiliation_overrides.yaml`, merged at run time with overrides winning. The 14 old `# manual` rows are migrated (12 with a placeholder reason, because the old marker stored none)
* The generator never touches the overrides file, refuses to run over a legacy marker, and warns about override logins no roster names; an offline test guards both committed files
* `refresh-affiliations.yml` regenerates the map on the 1st of each month and opens a PR as `github-actions[bot]` (API commit, signed, DCO) that can only contain the generated file

Commit 3, fetch hardening (`docs/fetch-hardening-plan.md` is the design record):

* A narrowed local run (`GITHUB_ORG` / `GITHUB_EXTRA_ORGS`) no longer prunes the datasets of orgs still in the registry, and the run says which registered orgs the environment left out
* GraphQL pagination halves its page size on a 502/504 and retries the same cursor instead of failing after three identical attempts; all paginated queries take `$pageSize`, batched rounds shrink together, the size recovers after three clean pages (`GITHUB_GRAPHQL_PAGE_SIZE`, `GITHUB_GRAPHQL_MIN_PAGE_SIZE`)
* `hiero-analytics seed-datasets` downloads the latest successful nightly run's dataset snapshot into `outputs/data/datasets/`, validated before writing, so a fresh clone's first run is a one-minute download instead of a cold fetch

**Related issue(s)**:

Fixes #536
Related: #524 (fetch quantification), #415 (pagination)

**Notes for reviewer**:

- Registry entry plus logo files, as `docs/adding-an-organisation.md` describes. All five CLPR governance participants (`edward-swirldslabs`, `hendrikebbers`, `ryjones`, `jwagantall`, `thelinuxfoundation`) were already resolved.
- Second commit refreshes `affiliations.yaml` from live signals with CLPR in the governed roster. It is the resolver's output reviewed row by row, not hand-edited: 15 people who left the governance config drop out, 8 new participants come in (two with no public signal stay `?`), `grigorov-georgi` goes from LimeChain to `?` because the automated July signal is gone and nothing current replaces it, `littletarzan` resolves to Independent from a personal email, and 9 role tags follow the live config. All 14 manual rows keep their values. A follow-up PR, stacked on this one, moves those rows into their own overrides file and refreshes `docs/affiliations.md`.
- Artwork: CLPR publishes no logo file in its repositories or on hashgraph.com/clpr, so the mark is a potrace vector trace of the LFDT-CLPR GitHub organisation avatar, the project's one official mark. Source, method and date are recorded in `web/public/brand/README.md`. It is mark-only (no wordmark), so the header reads as the spiral followed by "Analytics"; the org name stays in the switcher and the accessible label. If CLPR maintainers prefer a different file, swapping the two SVGs is all it takes.
- Budget: a trial cold fetch on 2026-10-14 measured 73 GraphQL points and 24 REST requests for the org (`docs/api-budget.md`, "A small org's first fetch"). Steady state will be a few points per run.
- The dashboard preview for this PR fetches live data rather than using the cache, because the registry changed and the base branch has no CLPR datasets.
- Commit 2: 12 of the 14 migrated override rows carry the reason "hand-set before the overrides file existed; reason not recorded"; the reason column is now required, so new rows will do better. Four overrides lock a value identical to the resolver's and are kept as confirmations. Before the first dispatch of `refresh-affiliations.yml`, turn on "Allow GitHub Actions to create and approve pull requests" (Settings > Actions > General); CI does not run on a PR the Actions token opens, so the workflow runs the offline file-guard tests before opening it, and close/reopen runs the full suite.
- Commit 3: the shrink only engages on a 5xx, so the happy path is byte-for-byte the same queries at `first:100`; points are charged per node so smaller pages cost the same budget. The per-repo `releases` loop has its own page guard and does not shrink (its batched path does). `seed-datasets` only ever downloads from the configured repository's own Actions artifacts and refuses non-flat zip entries, non-JSON files, oversized archives and a non-empty target without `--force`; exercised against the real nightly artifact (17 files, 121 MB unpacked, 8 MB download).
- `uv run pytest` (1329 passed, 96% coverage) and `uv run ruff check src tests` pass locally; `actionlint` is clean on the new workflow.

**Checklist**

- [x] I claimed the linked issue with `/assign` before starting (see [contributing guide](https://github.com/hiero-hackers/analytics/blob/main/CONTRIBUTING.md#workflow))
- [x] `uv run pytest` and `uv run ruff check src tests` pass locally
- [x] Tests added/updated for the change (mirroring the `src/` layout)
- [x] Commits are signed and signed-off: `git commit -S -s`
- [x] Docs updated if relevant
