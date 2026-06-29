"""GitHub API configuration constants.

Endpoints, authentication, rate-limiting, and concurrency settings used across
the data-source layer.
"""
import os

from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
BASE_URL = "https://api.github.com"

HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", 20))
REQUEST_DELAY_SECONDS = float(os.getenv("REQUEST_DELAY_SECONDS", 0.25))
SEARCH_REQUEST_DELAY_SECONDS = 1.0
SECONDARY_RATE_LIMIT_FALLBACK_SECONDS = 30

# Default concurrency for org-wide parallel fetches. Kept low because GitHub's
# secondary (abuse) rate limit is triggered by request burst/concurrency, not
# just hourly quota. Raise via env (e.g. GITHUB_MAX_WORKERS=6) for speed when the
# org is small or the token has generous limits; lower it when hitting 403s.
GITHUB_MAX_WORKERS = int(os.getenv("GITHUB_MAX_WORKERS", 3))
