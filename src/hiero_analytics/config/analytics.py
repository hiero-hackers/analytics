from hiero_analytics.domain.labels import ALL_ONBOARDING
DEFAULT_MODE: str = "org"  # "org" or "repo"

DEFAULT_ORG: str = "hiero-ledger"
DEFAULT_REPO: str = "hiero-ledger/hiero-sdk-python"

DEFAULT_LABELS: list[str] = sorted(ALL_ONBOARDING.labels)

DEFAULT_TIMEFRAME: str = "all"  # "all", "12m", "24m"

DEFAULT_INCLUDE_PULL_REQUESTS: bool = False