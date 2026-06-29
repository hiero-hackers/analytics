"""Tunable thresholds for the activity / governance analyses — one place to find them.

Recency windows gate *status* (active vs quiet); contribution counts are all-time
except the role-coverage ``*_recent`` columns. The network thresholds set how many
shared members a repo pair needs before they're linked (raise to thin a dense group).
"""

from __future__ import annotations

import os

# Recency windows (days).
ROLE_ACTIVE_DAYS = int(os.getenv("ROLE_ACTIVE_DAYS", "90"))  # "active vs quiet in a repo"
GONE_DARK_DAYS = int(os.getenv("GONE_DARK_DAYS", "180"))  # "no activity anywhere" / team quiet

# Review-load concentration: ignore repos with little recent review+merge volume.
LOAD_SHARE_MIN_ACTIONS = 20

# Maintainer-coverage flag: surface repos with at most this many *active* maintainers.
UNDERSTAFFED_MAX_ACTIVE_MAINTAINERS = 1

# Co-membership network: min shared members for a link, per role group.
ROLE_NETWORK_MIN_SHARED = {
    "maintainer": int(os.getenv("NETWORK_MIN_SHARED", "1")),
    "committer": 2,
    "triage": 1,
    "general": 4,
}

# All-contributors network: one link per this many repos (scales the threshold to org
# size, so a large org stays legible and a small one still shows its overlaps).
CONTRIBUTOR_NETWORK_REPOS_PER_LINK = 6
