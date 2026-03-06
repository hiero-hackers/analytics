from __future__ import annotations

import pandas as pd
from typing import Dict

from hiero_analytics.domain.labels import GOOD_FIRST_ISSUE
from hiero_analytics.metrics.label_metrics import label_metrics


def good_first_issue_metrics(
    df: pd.DataFrame,
) -> Dict[str, pd.DataFrame]:

    return label_metrics(df, GOOD_FIRST_ISSUE)