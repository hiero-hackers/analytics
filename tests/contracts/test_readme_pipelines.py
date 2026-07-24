"""Guard against drift between the pipeline registry and the README's pipeline table."""

import re
from pathlib import Path

from hiero_analytics.pipelines import PIPELINES

_README = Path(__file__).resolve().parents[2] / "README.md"


def test_readme_pipeline_table_matches_registry():
    """The README's pipeline table lists exactly the registered pipelines.

    The table rows are the only README lines shaped ``| `name` | ... |``, so any
    registered pipeline missing a row (or a stale row for a removed pipeline)
    fails here instead of drifting silently.
    """
    rows = set(re.findall(r"^\| `([a-z_]+)` \|", _README.read_text(), flags=re.MULTILINE))
    registered = {pipeline.name for pipeline in PIPELINES}

    assert rows == registered, (
        f"README pipeline table out of sync with the registry. "
        f"Missing from README: {sorted(registered - rows)}; stale in README: {sorted(rows - registered)}"
    )
