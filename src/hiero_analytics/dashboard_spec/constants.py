"""Spec constants shared by the family modules and the package assembly.

Kept apart from ``__init__`` because the family modules are imported *by* it —
a family reaching back into the package root would be a cycle.
"""

from __future__ import annotations

# Where a reader reports anything that looks wrong. The dashboard footer links
# it on every tab; the affiliations table reuses it for its contextual
# "Suggest a correction" action, since that table's data is hand-curated rather
# than computed.
PROJECT_ISSUES_URL = "https://github.com/hiero-hackers/analytics/issues"
