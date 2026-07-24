"""Community — Discord activity (manual export).

Pure data; see the package __init__ for assembly.
"""

from __future__ import annotations

CHART_MACRO = {
    "name": "Community",
    "charts": {
        "hiero-ledger": [
            {
                "id": "discord",
                "title": "Discord activity",
                "description": "Discord channel categories, monthly traffic, and recent activity.",
                "files": [
                    ("Channel categories", "hiero_discord_channel_categories.png"),
                    ("Monthly traffic", "hiero_discord_monthly_traffic.png"),
                    ("Recent activity (30d)", "hiero_discord_recent_activity_30d.png"),
                ],
            },
        ],
    },
}

CHART_NOTES = {
    "hiero_discord_channel_categories.png": "Discord message volume grouped by topic area, split into the last 90 days versus earlier history. "
    "From a manual Discord export (counts are as of the export date).",
    "hiero_discord_monthly_traffic.png": "Total Discord messages per month across the export's date range.",
    "hiero_discord_recent_activity_30d.png": "The five Discord channels with the most messages in the last 30 days (relative to the export snapshot date).",
}

CHART_METHODOLOGY = {}

WIDE_CHARTS: set[str] = set()
