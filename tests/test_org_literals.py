"""No organisation is named in code outside the org registry.

The point of ``config/orgs.py`` is that adding or renaming an org is one edit.
A string literal equal to a registered login anywhere else in ``src/`` is a
second place that edit would have to happen, and the one most likely to be
missed. Only exact literals are checked (via the AST), so prose that mentions
an org in a docstring, comment or longer message is fine.
"""

from __future__ import annotations

import ast
from pathlib import Path

from hiero_analytics.config.orgs import org_names

SRC = Path(__file__).resolve().parents[1] / "src" / "hiero_analytics"

# Files allowed to name orgs, each for a reason that is about the org's data,
# not about which orgs exist.
ALLOWED = {
    # The registry itself.
    "config/orgs.py",
    # The HIP coverage matrix's columns are repositories of the one org whose
    # proposals the HIPs tab tracks; they are that org's data, keyed by its name.
    "dashboard_spec/hips.py",
}


def _string_literals(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.lineno, node.value


def test_no_org_login_is_hardcoded_outside_the_registry():
    """Every exact string literal equal to a registered login lives in an allowed file."""
    logins = {name.lower() for name in org_names()}
    offenders = [
        f"{path.relative_to(SRC)}:{line}: {value!r}"
        for path in sorted(SRC.rglob("*.py"))
        if str(path.relative_to(SRC)) not in ALLOWED
        for line, value in _string_literals(path)
        if value.lower() in logins
    ]
    assert not offenders, "org logins hard-coded outside config/orgs.py:\n" + "\n".join(offenders)


def test_the_allowlist_has_no_stale_entries():
    """Each allowed file exists, so the list cannot silently outlive a refactor."""
    for relative in ALLOWED:
        assert (SRC / relative).exists(), relative
