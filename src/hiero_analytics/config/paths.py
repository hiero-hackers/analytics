from __future__ import annotations

from pathlib import Path

ORG = "hiero-ledger"

PROJECT_ROOT = Path(__file__).resolve().parents[3]

OUTPUTS_DIR = PROJECT_ROOT / "outputs"
LABEL_ANALYTICS_DIR = OUTPUTS_DIR / "label_analytics"

DATA_DIR = OUTPUTS_DIR / "data"
CHARTS_DIR = OUTPUTS_DIR / "charts"

def ensure_output_dirs() -> None:
    """
    Ensure output directories exist.
    Should be called by runner scripts before writing files.
    """
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    LABEL_ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)