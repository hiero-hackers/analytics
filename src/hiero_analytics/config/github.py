"""GitHub API configuration constants.

Endpoints, authentication, rate-limiting, and concurrency settings used across
the data-source layer.
"""

import os

from hiero_analytics.config.env import env_float, env_int
from hiero_analytics.config.orgs import ORGS

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
BASE_URL = "https://api.github.com"

HTTP_TIMEOUT_SECONDS = env_float("HTTP_TIMEOUT_SECONDS", 20.0, minimum=0.0)
# Fixed inter-request sleep, off by default: the adaptive concurrency limiter
# and secondary-rate-limit backoff pace requests properly, so a flat delay only
# adds wall-clock time. Set via env (e.g. REQUEST_DELAY_SECONDS=0.25) as an
# emergency brake if a token keeps tripping abuse limits.
REQUEST_DELAY_SECONDS = env_float("REQUEST_DELAY_SECONDS", 0.0, minimum=0.0)
SEARCH_REQUEST_DELAY_SECONDS = 1.0
SECONDARY_RATE_LIMIT_FALLBACK_SECONDS = 30

# How many repositories to combine into one GraphQL request via field aliases.
# Collapses network round-trips (cost in rate-limit points is roughly the sum of
# the parts either way). Kept moderate so per-query node/complexity limits stay
# far away even for issue-heavy repos.
GITHUB_GRAPHQL_BATCH_SIZE = env_int("GITHUB_GRAPHQL_BATCH_SIZE", 5, minimum=1)

# Nodes requested per GraphQL page. GitHub answers a query that runs too long with
# a 502/504, and retrying the identical page is futile, so pagination halves this
# on a server error (never below the floor), retries the same cursor, and doubles
# back up after a few clean pages. Smaller pages cost the same rate-limit points
# (charged per node) and only add round trips. The default of 100 is GitHub's
# per-connection maximum, so raising it has no effect.
GITHUB_GRAPHQL_PAGE_SIZE = env_int("GITHUB_GRAPHQL_PAGE_SIZE", 100, minimum=1)
# The smallest page the shrink-on-server-error loop will try before giving up and
# re-raising the error.
GITHUB_GRAPHQL_MIN_PAGE_SIZE = env_int("GITHUB_GRAPHQL_MIN_PAGE_SIZE", 10, minimum=1)

# Default concurrency for org-wide parallel fetches. GitHub's secondary (abuse)
# rate limit is triggered by request burst/concurrency, not just hourly quota,
# but the adaptive limiter shrinks concurrency on throttle and recovers on
# success, so a moderately higher default is safe. Lower via env
# (e.g. GITHUB_MAX_WORKERS=3) if a token keeps hitting 403s.
GITHUB_MAX_WORKERS = env_int("GITHUB_MAX_WORKERS", 6, minimum=1)

# Where HIP specifications live: the proposals repository and the directory of
# merged spec files inside it. The HIP-implementation pipeline parses each
# file's frontmatter into the canonical inventory that PR references are
# validated against.
# The default comes from the org registry (the profile with a
# ``hip_proposals_repo``); pipelines resolve it per org through
# ``config.orgs.hip_proposals_repo``. ``HIP_PROPOSALS_REPO`` overrides both.
HIP_PROPOSALS_REPO = os.getenv("HIP_PROPOSALS_REPO") or next(
    (profile.hip_proposals_repo for profile in ORGS if profile.hip_proposals_repo), ""
)
HIP_PROPOSALS_DIR = os.getenv("HIP_PROPOSALS_DIR", "HIP")
