"""Tunable thresholds for the activity / governance analyses — one place to find them.

Recency windows gate *status* (active vs quiet); contribution counts are all-time
except the role-coverage ``*_recent`` columns. The network thresholds set how many
shared members a repo pair needs before they're linked (raise to thin a dense group).
"""

from __future__ import annotations

from hiero_analytics.config.env import env_int

# Recency windows (days).
ROLE_ACTIVE_DAYS = env_int("ROLE_ACTIVE_DAYS", 90, minimum=1)  # "active vs quiet in a repo"
GONE_DARK_DAYS = env_int("GONE_DARK_DAYS", 180, minimum=1)  # "no activity anywhere" / team quiet

# Review-load concentration: ignore repos with little recent review+merge volume.
LOAD_SHARE_MIN_ACTIONS = 20

# Maintainer-coverage flag: surface repos with at most this many *active* maintainers.
UNDERSTAFFED_MAX_ACTIVE_MAINTAINERS = 1

# Co-membership network: min shared members for a link, per role group.
ROLE_NETWORK_MIN_SHARED = {
    "maintainer": env_int("NETWORK_MIN_SHARED", 1, minimum=1),
    "committer": 2,
    "triage": 1,
    "general": 4,
}

# All-contributors network: one link per this many repos (scales the threshold to org
# size, so a large org stays legible and a small one still shows its overlaps).
CONTRIBUTOR_NETWORK_REPOS_PER_LINK = 6

# Contributor activity heatmap: window length (months), rows shown, and the weight
# each action type contributes to a contributor's monthly score.
HEATMAP_MONTHS = 6
HEATMAP_TOP_ROWS = 25
ACTIVITY_WEIGHTS = {
    "issues": 2,
    "reviews": 3,
    "prs created": 3,
    "prs merged": 2,
}
