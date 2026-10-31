"""Column description contract re-exported from the export package.

This module re-exports `Column` and `column_spec` from `hiero_analytics.export.columns` so that the dashboard spec package
can depend on it without circular imports. Family modules should import
them from `hiero_analytics.dashboard_spec.columns`.
"""

from hiero_analytics.export.columns import Column, column_spec  # type: ignore[no-redef]

__all__ = ["Column", "column_spec"]
