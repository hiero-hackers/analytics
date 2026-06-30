"""Helpers for working with ``owner/repo`` identifiers."""

from __future__ import annotations


def bare_repo(name: str) -> str:
    """Return the repository name without its ``owner/`` prefix.

    Note: this collapses repos that share a name across owners (``a/foo`` and
    ``b/foo`` both become ``foo``). That's fine within a single-org analysis — every
    repo shares the org owner — but revisit here if cross-org data is ever mixed in
    one frame.
    """
    return name.split("/")[-1]
