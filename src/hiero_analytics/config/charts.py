"""
Defines configuration constants for styling and formatting charts in the analytics module. 
This includes default figure sizes, color palettes, font sizes, and grid settings to ensure a consistent look and feel across all visualizations.
"""
from __future__ import annotations

# --------------------------------------------------
# Figure configuration
# --------------------------------------------------

DEFAULT_DPI: int = 300
DEFAULT_FIGSIZE: tuple[int, int] = (12, 7)


# --------------------------------------------------
# Style configuration
# --------------------------------------------------

DEFAULT_STYLE: str = "seaborn-v0_8-whitegrid"

TITLE_FONT_SIZE: int = 14
LABEL_FONT_SIZE: int = 11
TICK_FONT_SIZE: int = 10
LEGEND_FONT_SIZE: int = 10


# --------------------------------------------------
# Grid configuration
# --------------------------------------------------

GRID_ENABLED: bool = True
GRID_ALPHA: float = 0.4
GRID_STYLE: str = "--"


# --------------------------------------------------
# Label color mapping
# --------------------------------------------------

LABEL_COLORS: dict[str, str] = {
    "good first issue": "#1f77b4",
    "skill: good first issue": "#1f77b4",
    "good first issue candidate": "#ff7f0e",
    "beginner": "#2ca02c",
    "help wanted": "#d62728",
}


# --------------------------------------------------
# Default palette
# --------------------------------------------------

DEFAULT_COLOR_PALETTE: list[str] = [
    "#1f77b4",
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
]