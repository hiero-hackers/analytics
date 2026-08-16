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

# Affiliation curation floor: below this share of resolved affiliations a role's
# diversity charts describe a minority of their own population, so the run warns
# rather than letting curation decay pass as a quietly shrinking employer count.
AFFILIATION_MIN_KNOWN_SHARE_PCT = env_int("AFFILIATION_MIN_KNOWN_SHARE_PCT", 60, minimum=0)

# Role co-membership networks: min shared members for a repo-repo link, per
# governance role (raise to thin a dense group into something readable).
ROLE_NETWORK_MIN_SHARED = {
    "maintainer": env_int("NETWORK_MIN_SHARED", 1, minimum=1),
    "committer": env_int("NETWORK_MIN_SHARED_COMMITTER", 1, minimum=1),
    "triage": env_int("NETWORK_MIN_SHARED_TRIAGE", 1, minimum=1),
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

# Difficulty pipelines: full window for the difficulty-over-time series, and a
# low worker count for the event-heavy timeline fetches (they hit the API
# hardest). The per-repo difficulty snapshots follow the shared activity
# periods (domain/periods.py) rather than their own window set.
DIFFICULTY_OVER_TIME_WINDOW_DAYS = 365
TIMELINE_MAX_WORKERS = 3

# Staleness-ratio bucket thresholds for the Releases tab's colored table
# column (days_since_last_release / a repo's own median release gap). A
# repo above STALENESS_OVERDUE_RATIO is flagged distinctly from one merely
# above STALENESS_WATCH_RATIO — "notably behind its own pace" vs "worth
# keeping an eye on" are different severities, not one bucket.
STALENESS_WATCH_RATIO = 1.0
STALENESS_OVERDUE_RATIO = 3.0

# The Hiero era began when the codebase moved to hiero-ledger (September
# 2024). HIP-implementation analytics count only PRs from this era — earlier
# references describe pre-migration (Hedera-era) work and are kept in the
# evidence tables flagged "pre-Hiero era" rather than counted.
HIERO_ERA_START = "2024-09-01"
