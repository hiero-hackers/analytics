# Examples

Standalone, runnable demo scripts showing how to call the `hiero_analytics`
data-source and analysis APIs directly. They are **not** part of the installable
package and are not imported by it — they live here so they don't ship with the
library.

Run them with the project environment (a `GITHUB_TOKEN` in your `.env` is needed
for the data-source examples — see the top-level README):

```bash
uv run python examples/data_sources/issues/fetch_issues_org.py
```

Layout mirrors the package: `examples/data_sources/…` and `examples/analysis/…`.
