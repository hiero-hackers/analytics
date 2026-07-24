"""Configuration package for hiero-analytics.

Importing any ``hiero_analytics.config.*`` module executes this package
first, so the ``.env`` load below is guaranteed to run before any config
module reads the environment (``GITHUB_ORG`` in ``paths``, ``GITHUB_TOKEN``
in ``github``, thresholds in ``analysis``) — regardless of which module is
imported first elsewhere.
"""

from dotenv import load_dotenv

load_dotenv()
