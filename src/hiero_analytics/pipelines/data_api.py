"""Emit the versioned JSON data API from existing outputs.

Like the dashboard, this is a pure re-render over tables the data pipelines
already wrote — it fetches nothing, so it is offline-capable and cheap. The
full run invokes it right before the dashboard; run it standalone to refresh
``outputs/data/api/`` after hand-editing or re-running a single pipeline.

See :mod:`hiero_analytics.export.data_api` for the API layout and the column
contract it enforces.
"""

from __future__ import annotations

import logging

from hiero_analytics.export.data_api import emit_data_api

logger = logging.getLogger(__name__)


def main() -> None:
    """Write ``outputs/data/api/<version>/`` from the produced tables."""
    manifest_path = emit_data_api()
    logger.info("Data API manifest written to %s", manifest_path)
