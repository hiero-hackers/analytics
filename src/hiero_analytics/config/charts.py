"""Colour constants shared by the chart data the dashboard draws.

The dashboard renders charts from the JSON chart documents the export layer
emits; the colours declared here travel in those documents (or in the spec
that builds them) so every view of the same category, difficulty or employer
agrees. Styling that only a rendered image needed went with the plotting
layer — layout and typography belong to the web app.
"""

from __future__ import annotations

# Colours for the semantic repository categories (see domain.repo_categories),
# used to colour the repository network. One distinct hue per category.
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

# Blue ramp for the HIP evidence levels, light to dark (export/hip_views). The
# web dashboard's coverage matrix renders the ``--heat-1``..``--heat-5`` tokens
# in web/src/app.css, which invert for dark mode; keep the light values here in
# step with those tokens so exported data and the matrix agree.
HIP_EVIDENCE_RAMP = ("#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#104281")

# Preserve the original domain colors for the analytics charts that already
# have established meaning in project discussions and screenshots.
DIFFICULTY_COLORS = {
    "Advanced": "#E78AC3",
    "Intermediate": "#FFD92F",
    "Beginner": "#8DA0CB",
    "Good First Issue": "#66C2A5",
    "Unknown": "#B3B3B3",
}

# Twenty qualitative swatches (derived from tab20, neutral greys replaced) for
# organisation-keyed charts; darker hues come first so adjacent, prominent
# employers stay easy to distinguish in dense stacked bars. Ranking employers
# onto the palette lives in analysis.affiliation.
SEGMENT_PALETTE = [
    "#1F77B4",
    "#FF7F0E",
    "#2CA02C",
    "#D62728",
    "#9467BD",
    "#8C564B",
    "#E377C2",
    "#BCBD22",
    "#17BECF",
    "#393B79",
    "#AEC7E8",
    "#FFBB78",
    "#98DF8A",
    "#FF9896",
    "#C5B0D5",
    "#C49C94",
    "#F7B6D2",
    "#DBDB8D",
    "#9EDAE5",
    "#8C6D31",
]
