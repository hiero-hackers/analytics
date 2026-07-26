# Architecture

How `hiero_analytics` is put together, for contributors. This is the top-down map;
each module's own docstring is the authoritative detail.

The system is a batch pipeline: **fetch** GitHub data → **analyze** it into tables →
**render** charts and emit a versioned JSON data API, which the web dashboard
(`web/`, a static Vite + React app) renders. It is an application, not a library —
its public surface is the `hiero-analytics` CLI, the data API, and the dashboard,
not an importable Python API.

## Layers

Packages form a strict, acyclic, downward-only dependency graph. Nothing in a lower
layer imports from a higher one (enforceable by reading imports; there are zero
violations today).

```
config, domain          base vocabulary — no internal dependencies
      ▲
data_sources            fetch + cache + persist GitHub data
      ▲
analysis                pure DataFrame transforms (no I/O, no network)
      ▲
plotting, export        render charts and emit the JSON data API
      ▲
dashboard_spec          declarative: which charts/tables the dashboard shows
      ▲
pipelines, cli          orchestration — wire a fetch → analysis → output run
```

- **`config`** — paths, env parsing (`env.py` clamps/validates), chart style
  constants, logging. `.env` is loaded once in `config/__init__`, before any
  config module reads the environment.
- **`domain`** — the shared vocabulary that everything agrees on: `roles`
  (`ROLE_PRIORITY`, `permission_to_role`), `repo_categories`, `bots`, `labels`,
  `periods` (the rolling activity windows), `recency`, `repos`. Pure data and
  predicates; no I/O. If two layers need to agree on a concept, it lives here.
- **`data_sources`** — everything touching GitHub. Transport (`github_client` owns
  all retry/backoff/rate-limit handling; `rate_limit` is a pure policy;
  `adaptive_limiter` an AIMD concurrency limiter), ingestion (`github_ingest/`),
  persistence (`dataset_store`, `cache`, `serialization`), `models`, and
  `governance_config`.
- **`analysis`** — pure transforms from record lists / DataFrames to output
  DataFrames. No network, no file I/O beyond what it is handed. This is the most
  heavily unit-tested layer and the safest to refactor.
- **`plotting` / `export`** — `plotting` renders matplotlib charts (all figure
  creation flows through `plotting/base`, which guarantees figures are closed even
  on error); `export/save` writes CSVs (+ a freshness sidecar) and
  `export/data_api` emits the JSON documents the web dashboard fetches. Both are
  data-agnostic beyond `config`, `domain`, and the spec.
- **`dashboard_spec`** — pure data: one module per dashboard *family*
  (`contributors`, `governance`, `onboarding`, `hips`, `security`, `community`)
  declaring its chart macro, notes, methodology, and optionally its table sections,
  its own "how to read this" glossary, and a module that builds views a table or
  chart gallery cannot express. The package `__init__` assembles them and fails
  loudly if two families claim the same chart.
- **`pipelines` / `cli`** — the orchestration layer. Each pipeline reads a fetch,
  runs analysis, and writes outputs.

## The three registries

Extensibility flows through three declarative registries rather than scattered
special-casing. Adding a capability means adding a registry entry, not editing a
dispatcher.

**Pipeline registry** (`pipelines/__init__.py`). Each `Pipeline` declares its name
(= module name = CLI subcommand), description, CLI options (`org`/`repo`), whether it
is `offline`-capable, and whether it is in the default full run. Both the CLI
(`cli.py`) and the orchestrator (`pipelines/run_all.py`) are driven by this list.
*To add a pipeline:* create `pipelines/<name>.py` with a `main()`, append one
`Pipeline(...)` entry.

**Ingestion resource registry** (`data_sources/github_ingest/`). Each
`OrgIncrementalResource` declares a fetched dataset's name, model, record identity
(`key_of`), and watermark accessor (`updated_at_of`). The shared skeleton
(`incremental.py`) owns the fetch shape — full fetch on first run, guarded
since-delta afterwards, periodic forced refresh, dataset-store persistence — so a new
resource is a declaration plus its query plumbing, not another copy of the skeleton.
See `ORG_INCREMENTAL_RESOURCES`.

**Dashboard family registry** (`dashboard_spec/__init__.py`). A family module is a
pure-data description of one dashboard tab; the package discovers what each one
opts into by attribute, so the renderer never names a family. `SECTION_SPECS` adds
filterable tables (`TABLE_FAMILIES`); `GLOSSARY_HTML` replaces the shared column
glossary with the tab's own (`MACRO_GLOSSARIES`); `CUSTOM_VIEWS_MODULE` names a
module exposing `build_views(org, org_data_dir)` for views that are neither a
table nor a chart gallery (`CUSTOM_VIEW_MODULES`) — the HIPs tab's governance
board and coverage matrix are built that way, in `export/hip_views.py`.
*To add a family:* create the module, list it in `_FAMILIES`.

## Data flow and persistence

**The data API.** After the pipelines write their tables, `export/data_api.py`
emits `outputs/data/api/v1/` — one JSON document per spec-listed section plus a
`manifest.json` (orgs, sections, chart sections, bespoke views, per-macro
glossaries, provenance). It is the consumption
contract for everything downstream of the pipelines (the web dashboard,
notebooks, external tools), and it enforces the producer↔spec agreement: a
produced table missing a spec-declared column fails the emit, so a renamed
output is a red build rather than a silently blank dashboard column. Breaking
shape changes bump the version directory; `v1` is additive-only.

**The web dashboard.** `web/` is a static Vite + React app deployed at the Pages
site root with `data/api/` and `charts/` nested beneath it. It is manifest-driven:
it renders whatever orgs, sections, chart sections, and metric tiles the API
lists, so adding analytics rarely requires frontend changes. It imports the
long-standing dashboard stylesheet (`web/src/dashboard.css`) unchanged.


A pipeline's `main(org=ORG)` obtains a GitHub client + output dirs from
`pipelines/_shared` (one shared client per process), fetches records, runs `analysis`
transforms, and writes CSVs/PNGs under `outputs/data/org/<org>/` and
`outputs/charts/org/<org>/`.

Fetching is **incremental** and has two persistence layers, by design:

- **`cache`** — a short-TTL cache for repeated within-day runs (e.g. per-repo
  fetches). Disposable.
- **`dataset_store`** — the durable "system of record" for org-wide datasets. Keeps
  full history; later runs fetch only the delta since a watermark and merge it
  (idempotent upsert). Partial org failures *hold* the watermark so the gap refetches
  next run rather than being lost; any other delta failure falls back to a full fetch.
  Reuse is bounded (`load_or_fetch` refuses data older than a few days), and a periodic
  forced full refresh self-heals drift. Both stores fail safe: a corrupt file is a
  cache miss, and version bumps invalidate.

`run_all` executes the default pipelines in order, isolating failures (one bad
pipeline can't sink the run; CI still sees a non-zero exit), then emits the data
API once.

## Provenance

Nothing generated is committed, and each Pages deploy overwrites the last, so an
artifact has to carry its own identity. `provenance` resolves two facts — the
oldest dataset watermark (`data as of`) and the code revision (`GITHUB_SHA` in
CI, `git rev-parse` locally, suffixed `-dirty` on an uncommitted tree) — and they
are applied in three places:

- **Every PNG** gets a footer via `plotting/style.draw_provenance_footer`, applied
  in `plotting/base.save_and_close` because every chart reaches disk through it.
  The row count comes from the caller, which already holds the frame. The footer
  never raises: an unstamped chart beats a failed render.
- **The dashboard** stamps the generation time and revision in its page footer
  (from the manifest's provenance block), on top of the per-section `data as of`
  badges fed by the `.meta.json` sidecars that `export/save.write_output_meta`
  writes next to each CSV. CSVs downloaded from a table carry the same stamp as
  `#` comment lines.
- **The dataset snapshot** is archived per CI run as an immutable artifact,
  carrying a `SNAPSHOT.json` manifest (revision, per-dataset watermark and
  SHA-256, and any failed pipelines). This is distinct from the Actions *cache*
  of the same directory: the cache is mutable, evictable, and only reachable by
  the next run, so it can't answer "which data drew this chart?".

## Multi-org

Output dirs are per-org, so multiple orgs coexist. `config.paths.EXTRA_ORGS` is the
single "also render this org" concept (consumed by both `run_all`'s contributor pass
and the heatmap). Governance is per-org: `fetch_governance_config(org)` resolves each
org's source from `GOVERNANCE_CONFIG_URLS` and snapshots it under an org-scoped path;
an org with no configured source is *ungoverned* (empty config — it never inherits
another org's roles).

## The dashboard contract

The data API is assembled by `export/data_api` from whatever CSVs/PNGs exist,
following `dashboard_spec`. The join key between producer (a pipeline) and consumer
(the spec) is the **output filename** — a fragile, stringly-typed seam. Two test
tiers guard it:

- `tests/dashboard_spec/` — internal spec consistency (every note/methodology entry
  references a listed chart; section groups cover the declared sections).
- `tests/contracts/test_output_contract.py` — runs the whole default pipeline set
  against synthetic fetches into a temp `outputs/` and asserts every spec-listed CSV
  and macro PNG is actually produced (and no orphans), and that the API lists a
  document for every produced section. This is what makes a renamed output fail
  loudly instead of silently blanking a dashboard section.

Every CSV is written with a `<name>.csv.meta.json` freshness sidecar; each API
section document carries the sidecar's timestamp and a `stale` flag past the
refresh cadence, which the dashboard shows as a per-section "data as of …" badge —
so a silently-reused stale CSV is visible to viewers.

## Test conventions

`tests/` mirrors `src/` package-for-package, with one addition: `tests/contracts/`
holds the cross-layer tests (README ↔ pipeline registry, outputs ↔ dashboard spec).
Analysis tests feed DataFrames into pure functions (robust to refactor); pipeline
tests are integration-style, stubbing the fetch layer at the pipeline module's
namespace and asserting the output files. Coverage floor is enforced in CI.

## Where things commonly go

| Task | Touch |
|---|---|
| Add a chart | its family module in `dashboard_spec/` + the producing pipeline |
| Add a chart *form* | a `plot_*` primitive in `plotting/` (pipelines never touch matplotlib) |
| Add a bespoke dashboard view | `CUSTOM_VIEWS_MODULE` on the family + a `build_views()` module returning pure data |
| Add a pipeline | `pipelines/<name>.py` + one `Pipeline` entry in `pipelines/__init__.py` |
| Add a fetched resource | `models` + `queries/` + `github_ingest/<x>.py` + one `OrgIncrementalResource` |
| A concept two layers share | `domain/` |
| Tune a threshold/window | `config/analysis.py` |
| Consume outputs programmatically | `outputs/data/api/v1/` (emitted by `export/data_api.py`) |
