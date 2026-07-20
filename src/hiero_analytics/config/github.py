"""GitHub API configuration constants.

Endpoints, authentication, rate-limiting, and concurrency settings used across
the data-source layer.
"""

import os

from dotenv import load_dotenv

from hiero_analytics.config.env import env_float, env_int

load_dotenv()

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
GITHUB_GRAPHQL_BATCH_SIZE = env_int("GITHUB_GRAPHQL_BATCH_SIZE", 10, minimum=1)

# Default concurrency for org-wide parallel fetches. GitHub's secondary (abuse)
# rate limit is triggered by request burst/concurrency, not just hourly quota,
# but the adaptive limiter shrinks concurrency on throttle and recovers on
# success, so a moderately higher default is safe. Lower via env
# (e.g. GITHUB_MAX_WORKERS=3) if a token keeps hitting 403s.
GITHUB_MAX_WORKERS = env_int("GITHUB_MAX_WORKERS", 6, minimum=1)
