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

# Inter, vendored as static TTFs in `plotting/fonts` and registered by
# `plotting.style.apply_style`. The web dashboard loads the same typeface (see
# the `--font-stack` token in web/src/app.css), so a chart PNG embedded in a
# card is set in the type around it rather than in matplotlib's DejaVu Sans.
# Only Regular (400) and SemiBold (600) are shipped — the two weights the
# charts actually ask for — so requesting any other weight falls through the
# stack below.
FONT_FAMILY: str = "Inter"

# Resolved in order when a glyph or weight is missing from Inter. DejaVu Sans
# ships with matplotlib, so the last entry always resolves and a font that
# failed to register degrades to the old typeface instead of a broken render.
FONT_FALLBACKS: tuple[str, ...] = ("DejaVu Sans",)

LABEL_FONT_SIZE: int = 11
TICK_FONT_SIZE: int = 10
LEGEND_FONT_SIZE: int = 10
ANNOTATION_FONT_SIZE: int = 10
CENTER_TOTAL_FONT_SIZE: int = 20
FONT_WEIGHT_SEMIBOLD: str = "semibold"

# --------------------------------------------------
# Surface + typography colors
# --------------------------------------------------
# These mirror the semantic tokens in web/src/app.css, so a chart reads as part
# of the card it sits in rather than as a pasted-in image. Keep them in step
# with that stylesheet's `:root` block.
#
# The figure ground is `--surface`, the same white as `.chart img`'s background,
# which is what lets the PNG blend into its card with no visible plate edge.
FIGURE_BACKGROUND_COLOR = "#FFFFFF"  # --surface
PLOT_BACKGROUND_COLOR = "#FFFFFF"  # --surface
TITLE_COLOR = "#1B1B1B"  # --ink
# A notch lighter than --ink: in-plot labels sit directly on the data, where the
# full-strength ink of a heading reads as heavy.
TEXT_COLOR = "#333333"
MUTED_TEXT_COLOR = "#666666"  # --muted
AXIS_LINE_COLOR = "#E6E6E6"  # --edge
CARD_BORDER_COLOR = "#E6E6E6"  # --edge

# --------------------------------------------------
# Grid styling
# --------------------------------------------------
GRID_ENABLED: bool = True
GRID_ALPHA: float = 1.0
GRID_STYLE: str = "-"
GRID_COLOR: str = "#EEEEEE"  # --edge-faint
GRID_LINE_WIDTH: float = 0.8

# --------------------------------------------------
# Legend styling
# --------------------------------------------------
LEGEND_BACKGROUND_COLOR = "#FFFFFF"  # --surface
LEGEND_EDGE_COLOR = "#E6E6E6"  # --edge
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
MUTED_HISTORICAL_COLOR = "#CCCCCC"  # --edge-strong

# Dashed threshold/reference lines (e.g. a 50% majority marker) and their labels.
REFERENCE_LINE_COLOR = "#444444"

# Small text badges (endpoint pills) and the shared card-edge stroke width used
# by badge boxes and legend frames.
BADGE_FONT_SIZE = 9
CARD_EDGE_LINE_WIDTH = 0.9

# --------------------------------------------------
# Provenance footer
# --------------------------------------------------
# The data/code/row-count stamp every figure carries (see
# `hiero_analytics.provenance`). Sized and faded to read as a caption: legible
# when looked for, unobtrusive when reading the data. Positioned in figure
# coordinates at the bottom-right, inset from the edge so `bbox_inches="tight"`
# does not crop it flush against the border.
FOOTER_FONT_SIZE = 7
FOOTER_ALPHA = 0.8
FOOTER_X = 0.995
FOOTER_Y = 0.006

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

# Colours for the semantic repository categories (see domain.repo_categories),
# used to colour the maintainer network. One distinct hue per category.
# Blue ramp shared by the HIP coverage-matrix cells, their legend, and the
# adoption-funnel bands, light to dark. The matrix's ``.hipmx td.m1``-``.m5``
# CSS classes in export/assets/dashboard.css mirror these values — keep them
# in step.
HIP_EVIDENCE_RAMP = ("#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#104281")

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
    "General User": "#94A3B8",  # muted slate
    "Triage": "#60B8D4",  # sky blue
    "Committer": "#2A9D8F",  # teal
    "Maintainer": "#E76F51",  # coral
}


SCORECARD_CHECK_COLORS = {
    "Maintained": "#1F77B4",
    "Code-Review": "#FF7F0E",
    "CII-Best-Practices": "#2CA02C",
    "Dangerous-Workflow": "#D62728",
    "Binary-Artifacts": "#9467BD",
    "Token-Permissions": "#8C564B",
    "Pinned-Dependencies": "#E377C2",
    "Fuzzing": "#7F7F7F",
    "License": "#BCBD22",
    "Signed-Releases": "#17BECF",
    "Security-Policy": "#003f5c",
    "Branch-Protection": "#ffa600",
    "Packaging": "#58508d",
    "SAST": "#ff6361",
}

# Contributor activity heatmap: the intensity colour scale plus the surrounding
# chrome colours (figure/axes background, cell text, ticks).
ACTIVITY_HEATMAP_CMAP = "RdYlGn"
ACTIVITY_HEATMAP_PALETTE = {
    "figure_bg": FIGURE_BACKGROUND_COLOR,
    "axes_bg": PLOT_BACKGROUND_COLOR,
    "text_dark": TITLE_COLOR,
    "text_light": "#FFFFFF",
    "tick": MUTED_TEXT_COLOR,
}

# Compliance / Codeowners status colors.
CODEOWNER_STATUS_COLORS = {
    "Present": "#2A9D8F",  # teal
    "Missing": "#E76F51",  # coral
}

RUNNER_STATUS_COLORS = {
    "Self-Hosted": "#2A9D8F",  # teal
    "Standard": "#E76F51",  # coral
    "Indeterminate": "#94A3B8",  # slate
}
