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
REQUEST_DELAY_SECONDS = env_float("REQUEST_DELAY_SECONDS", 0.25, minimum=0.0)
SEARCH_REQUEST_DELAY_SECONDS = 1.0
SECONDARY_RATE_LIMIT_FALLBACK_SECONDS = 30

# Default concurrency for org-wide parallel fetches. Kept low because GitHub's
# secondary (abuse) rate limit is triggered by request burst/concurrency, not
# just hourly quota. Raise via env (e.g. GITHUB_MAX_WORKERS=6) for speed when the
# org is small or the token has generous limits; lower it when hitting 403s.
GITHUB_MAX_WORKERS = env_int("GITHUB_MAX_WORKERS", 3, minimum=1)
