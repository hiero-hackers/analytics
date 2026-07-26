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

CHART_METHODOLOGY = {
    "hiero_discord_channel_categories.png": [
        "Read the manually exported Discord message archive from the gitignored inputs directory.",
        "Group channels into topic areas and count messages in each.",
        (
            "Split each area into the last 90 days versus earlier history, relative to the export date — "
            "not to today — so a formerly busy area reads differently from a currently busy one."
        ),
    ],
    "hiero_discord_monthly_traffic.png": [
        "Read the manually exported Discord message archive.",
        "Bucket every message by calendar month across the export's date range.",
        "Plot the monthly totals; the series ends at the export date, not at today.",
    ],
    "hiero_discord_recent_activity_30d.png": [
        "Read the manually exported Discord message archive.",
        "Count messages per channel in the 30 days before the export's snapshot date.",
        "Keep the five busiest channels.",
    ],
}

WIDE_CHARTS: set[str] = set()

# This tab's "how to read this". Prose only; *asterisks* mark emphasis.
GLOSSARY = {
    "title": "How to read this tab — what the numbers mean",
    "layout": "notes",
    "terms": [
        {
            "term": "What is measured.",
            "definition": (
                "Discord message counts from the community server, grouped by channel and by month. "
                "Messages are counted; participants are not identified anywhere on this tab."
            ),
        },
        {
            "term": "Where the data comes from.",
            "definition": (
                "A *manual export*, unlike every other tab — Discord is not fetched on the scheduled "
                "refresh. Every figure is as of the export date, so “last 30 days” means the 30 days "
                "before that snapshot, not before today. An out-of-date export silently ages."
            ),
        },
        {
            "term": "Channel categories.",
            "definition": (
                "Message volume grouped by topic area, split into the last 90 days versus earlier "
                "history — so a channel that was once busy reads differently from one busy now."
            ),
        },
        {
            "term": "What this tab cannot tell you.",
            "definition": (
                "Volume is not health: a channel can be busy with one long thread or quiet because its "
                "work moved to GitHub. Nothing here connects a Discord account to a GitHub login."
            ),
        },
    ],
}
