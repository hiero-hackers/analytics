"""Reading generated artifacts back for rendering: CSVs, freshness, data URIs.

The dashboard renderers (the generic one and each feature's section builder)
all need the same three things — load a produced CSV, stamp a section with its
freshness sidecar, and inline a payload as a ``data:`` URI for a download.
Keeping them here means the strftime format, the staleness threshold, and the
MIME strings exist once.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

# A section counts as stale when its data is older than the scheduled refresh
# cadence (daily) plus slack for a slow run.
STALE_AFTER = timedelta(hours=36)


def load_csv(path: Path) -> pd.DataFrame:
    """Read a produced CSV, or an empty frame if it doesn't exist."""
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def generated_at(path: Path) -> datetime | None:
    """Read an artifact's freshness sidecar, or None if absent/unreadable."""
    meta_path = Path(f"{path}.meta.json")
    if not meta_path.exists():
        return None
    try:
        return datetime.fromisoformat(json.loads(meta_path.read_text(encoding="utf-8"))["generated_at"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return None


def stamp_freshness(section: dict, source: Path) -> None:
    """Attach ``data_as_of``/``stale`` to a section from its source's sidecar."""
    stamp = generated_at(source)
    if stamp is None:
        return
    section["data_as_of"] = stamp.strftime("%Y-%m-%d %H:%M UTC")
    section["stale"] = datetime.now(UTC) - stamp > STALE_AFTER


def data_uri(payload: bytes | str, mime: str) -> str:
    """Base64 ``data:`` URI, so the dashboard stays a single self-contained file."""
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def csv_data_uri(payload: bytes | str) -> str:
    """``data:`` URI for a CSV download."""
    return data_uri(payload, "text/csv")


def png_data_uri(path: Path) -> str | None:
    """``data:`` URI for a chart PNG, or None when the file is missing."""
    return data_uri(path.read_bytes(), "image/png") if path.exists() else None
