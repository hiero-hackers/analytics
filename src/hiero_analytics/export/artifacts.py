"""Reading generated artifacts back for export.

The pipelines write CSVs; the data API and the bespoke view builders read them
again. A missing file is normal (its pipeline may not have run, or the org may
not have that data), so it reads as an empty frame rather than an error.

Freshness lives with the API emitter, which reads each artifact's
``.meta.json`` sidecar directly; base64 ``data:`` URI helpers retired with the
self-contained HTML dashboard.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_csv(path: Path) -> pd.DataFrame:
    """Read a produced CSV, or an empty frame if it doesn't exist."""
    return pd.read_csv(path) if path.exists() else pd.DataFrame()
