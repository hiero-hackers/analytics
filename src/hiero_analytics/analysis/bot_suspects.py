"""Build the bot-suspects review table.

``is_bot_login`` excludes named/suffixed automation accounts from people
metrics, but a login like ``hiero-automation`` or ``sdk-release-ci`` slips
through it and counts as a person in contributor tables, heatmaps, and
diversity metrics until someone happens to notice and adds it to
``BOT_LOGINS``. This sweeps every contributor login that showed up in
activity, flags the ones matching a weaker bot-ish signal, and writes them
out for a maintainer to confirm — mirroring how
``hip_implementation``'s ``hip_unknown_references.csv`` keeps unmatched HIP
numbers for review instead of silently dropping or counting them.

Suspects stay in the people metrics; nothing here removes or discounts them.
False positives in the output are acceptable (a real name can trip a
signal); the point is to surface candidates for ``BOT_LOGINS``, not to make
the exclusion call automatically. A login a maintainer confirms is a real
person, not a bot, goes in ``data/bot_suspect_dismissals.yaml`` (mirroring
``affiliations.yaml``'s hand-maintained-file pattern) so it stops reappearing
every run — see ``load_dismissed_suspects``.
"""

from __future__ import annotations

import logging

import pandas as pd

from hiero_analytics.config.paths import SRC
from hiero_analytics.data_sources.models import ContributorActivityRecord
from hiero_analytics.domain.bots import bot_suspect_signal

logger = logging.getLogger(__name__)

_SUSPECT_COLUMNS = ["login", "signal"]

DISMISSALS_PATH = SRC / "data" / "bot_suspect_dismissals.yaml"


def load_dismissed_suspects(path=DISMISSALS_PATH) -> set[str]:
    """Lowercased logins a maintainer has confirmed are real people, not bots.

    One bare login per line (comments and blank lines ignored) — see the file
    itself for the format. Missing file just means nothing's been dismissed yet.
    """
    if not path.exists():
        logger.warning("Bot-suspect dismissals file not found: %s", path)
        return set()

    dismissed: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        body = raw.split("#", 1)[0].strip().lower()
        if body:
            dismissed.add(body)
    return dismissed


def build_bot_suspects(
    records: list[ContributorActivityRecord],
    dismissed: set[str] | None = None,
) -> pd.DataFrame:
    """Distinct contributor logins that trip a weak bot signal, for review.

    One row per distinct login (case-insensitive), sorted alphabetically.
    Logins ``is_bot_login`` already excludes never appear here — they're
    automation accounts by the canonical policy already, not suspects. Logins
    in ``dismissed`` (default: ``load_dismissed_suspects()``) are skipped too —
    a maintainer already looked and confirmed they're people.
    """
    if dismissed is None:
        dismissed = load_dismissed_suspects()
    logins = {record.actor.strip().lower() for record in records if record.actor}
    rows = [
        {"login": login, "signal": signal}
        for login in logins
        if login not in dismissed and (signal := bot_suspect_signal(login)) is not None
    ]
    if not rows:
        return pd.DataFrame(columns=_SUSPECT_COLUMNS)
    return pd.DataFrame(rows, columns=_SUSPECT_COLUMNS).sort_values("login").reset_index(drop=True)
