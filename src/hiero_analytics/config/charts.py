"""Shared chart styling constants for the analytics plotting layer."""

from __future__ import annotations

# --------------------------------------------------
# Figure configuration
# --------------------------------------------------
DEFAULT_DPI: int = 300
DEFAULT_FIGSIZE: tuple[int, int] = (12, 7)

# --------------------------------------------------
# Base style
# --------------------------------------------------
DEFAULT_STYLE: str = "default"
FONT_FAMILY: str = "DejaVu Sans"
TITLE_FONT_SIZE: int = 16
LABEL_FONT_SIZE: int = 11
TICK_FONT_SIZE: int = 10
LEGEND_FONT_SIZE: int = 10
ANNOTATION_FONT_SIZE: int = 10
CENTER_TOTAL_FONT_SIZE: int = 20
FONT_WEIGHT_SEMIBOLD: str = "semibold"

# --------------------------------------------------
# Surface + typography colors
# --------------------------------------------------
FIGURE_BACKGROUND_COLOR = "#F6F8FB"
PLOT_BACKGROUND_COLOR = "#FFFFFF"
TITLE_COLOR = "#0F172A"
TEXT_COLOR = "#334155"
MUTED_TEXT_COLOR = "#64748B"
AXIS_LINE_COLOR = "#D7E0EA"
CARD_BORDER_COLOR = "#DCE5EF"

# --------------------------------------------------
# Grid styling
# --------------------------------------------------
GRID_ENABLED: bool = True
GRID_ALPHA: float = 1.0
GRID_STYLE: str = "-"
GRID_COLOR: str = "#E8EEF5"
GRID_LINE_WIDTH: float = 0.8

# --------------------------------------------------
# Legend styling
# --------------------------------------------------
LEGEND_BACKGROUND_COLOR = "#FFFFFF"
LEGEND_EDGE_COLOR = "#E2E8F0"
LEGEND_BOX_STYLE = "round,pad=0.35,rounding_size=1.4"

# --------------------------------------------------
# Annotation styling
# --------------------------------------------------
ENDPOINT_LABEL_BOX_STYLE = "round,pad=0.28,rounding_size=0.8"

# --------------------------------------------------
# Line / time-series styling
# --------------------------------------------------
LINE_WIDTH: float = 2.6
LINE_MARKER_SIZE: int = 7
LINE_MARKER_EDGE_WIDTH: int = 2
LINE_FILL_ALPHA: float = 0.08

# Muted neutral used to background "earlier" / context series so the
# accent color carries the eye to the recent / live portion of a chart.
MUTED_HISTORICAL_COLOR = "#CBD5E1"

# --------------------------------------------------
# Donut / pie styling
# --------------------------------------------------
DONUT_START_ANGLE = 110
DONUT_RADIUS = 0.92
DONUT_WIDTH = 0.34
DONUT_PERCENTAGE_DISTANCE = 0.8
DONUT_EDGE_LINE_WIDTH = 2.0

# --------------------------------------------------
# Accent palette for charts without a domain-specific color mapping
# --------------------------------------------------
PRIMARY_PALETTE = [
    "#F97316",
    "#14B8A6",
    "#0EA5E9",
    "#F59E0B",
    "#EF4444",
]

# Colours for the semantic repository categories (see analysis.repo_categories),
# used to colour the maintainer network. One distinct hue per category.
REPO_CATEGORY_COLORS = {
    "SDKs": "#0EA5E9",
    "Identity / DID": "#8B5CF6",
    "Core network": "#F97316",
    "EVM / smart contracts": "#14B8A6",
    "Tooling / DevEx": "#F59E0B",
    "Governance": "#EF4444",
    "Docs / Web": "#64748B",
    "Apps / Integrations": "#EC4899",
    "Other": "#94A3B8",
}

# Preserve the original domain colors for the analytics charts that already
# have established meaning in project discussions and screenshots.
DIFFICULTY_COLORS = {
    "Advanced": "#E78AC3",
    "Intermediate": "#FFD92F",
    "Beginner": "#8DA0CB",
    "Good First Issue": "#66C2A5",
    "Unknown": "#B3B3B3",
}

# Onboarding charts already use these colors across the existing exports.
ONBOARDING_COLORS = {
    "Good First Issues": "#2E749F",
    "Good First Issue Candidates": "#D8A251",
}

# State lines keep their original semantic mapping as well.
STATE_COLORS = {
    "total": "#3D3D3D",
    "closed": "#28A197",
    "open": "#F46A25",
}

MAINTAINER_PIPELINE_COLORS = {
    "General User": "#94A3B8",   # muted slate
    "Triage":       "#60B8D4",   # sky blue
    "Committer":    "#2A9D8F",   # teal
    "Maintainer":   "#E76F51",   # coral
}


SCORECARD_CHECK_COLORS = {
    "Maintained":         "#1F77B4",
    "Code-Review":        "#FF7F0E",
    "CII-Best-Practices": "#2CA02C",
    "Dangerous-Workflow": "#D62728",
    "Binary-Artifacts":   "#9467BD",
    "Token-Permissions":  "#8C564B",
    "Pinned-Dependencies":"#E377C2",
    "Fuzzing":            "#7F7F7F",
    "License":            "#BCBD22",
    "Signed-Releases":    "#17BECF",
    "Security-Policy":    "#003f5c",
    "Branch-Protection":  "#ffa600",
    "Packaging":          "#58508d",
    "SAST":               "#ff6361",
    "Vulnerabilities":    "#8b0000",
}

# Contributor activity heatmap: the intensity colour scale plus the surrounding
# chrome colours (figure/axes background, cell text, ticks).
ACTIVITY_HEATMAP_CMAP = "RdYlGn"
ACTIVITY_HEATMAP_PALETTE = {
    "figure_bg": "#F6F8FB",
    "axes_bg": "#FFFFFF",
    "text_dark": "#0F172A",
    "text_light": "#FFFFFF",
    "tick": "#64748B",
}