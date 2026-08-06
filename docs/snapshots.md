# Snapshot archive

Every successful scheduled refresh appends its data API to the orphan branch
`data/snapshots`, so the dashboard has a queryable, diffable history instead of
only its latest state.

## Layout

The branch's working tree holds **one** snapshot — the most recent:

```
api/v1/                    the emitted JSON API, exactly as published
  manifest.json
  <org>/<section>.json
SNAPSHOT.json              the run's provenance: git sha, run id, per-dataset
                           watermarks and SHA-256s, failed pipelines
```

History lives in the commits, not in dated directories. Each commit message
carries the lookup keys:

```
snapshot: 2026-08-06 run 31090950169 code 8930636
```

Chart PNGs are deliberately excluded: they are heavy, and the numbers behind
them are already in the JSON.

## Reading it

```bash
# The latest snapshot's manifest
git show data/snapshots:api/v1/manifest.json

# The snapshot as of a date (rev-list finds the last commit before it)
SHA=$(git rev-list -1 --before=2026-08-01 origin/data/snapshots)
git show "$SHA:api/v1/hiero-ledger/repo.json"

# What changed between two runs
git diff <sha1> <sha2> -- api/v1/

# Just the section list, without checking anything out
git show <sha>:api/v1/manifest.json | jq '.orgs | keys'
```

Fetch the branch first if you have not already — it shares no history with
`main`, so a normal clone does not carry it:

```bash
git fetch origin data/snapshots
```

## Reading a snapshot's shape

Snapshots accumulate across API versions. Every one carries its own
`manifest.json` with the API `version` field, so a consumer reading a year-old
snapshot can tell what shape it holds rather than assuming today's. Check the
version before parsing anything older than the current release.

## Guarantees and non-guarantees

- **Only published data is archived.** The archive job runs after a successful
  refresh, so a run with failed pipelines never enters the history.
- **Re-runs are safe.** A run whose output is byte-identical to the branch tip
  commits nothing, so replays and manual dispatches do not create noise.
- **Deletions propagate.** The tree is cleared before each snapshot is written,
  so a section removed from the spec disappears from the latest snapshot rather
  than lingering as an orphan. Earlier commits keep it, which is the point.
- **No retention policy yet.** One snapshot is ~3.5 MB of JSON across ~20 files,
  but consecutive snapshots are near-identical and git packs the deltas: a
  rehearsal of two snapshots (3.2 MB each on disk) packed to 632 KB of history
  in total. At the 5-day cadence that is a few MB a year, so there is nothing to
  manage yet. Revisit if the branch gets large; it can be pruned or rewritten
  later without touching `main`.

## Adding a consumer

Read the branch rather than re-inventing persistence. Anything that needs
"what did this look like N weeks ago" — score trends, weekly digests,
regression detection on published metrics — should source it here.
