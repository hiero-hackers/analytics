"""GraphQL query-document loading, with shared-fragment splicing."""

from __future__ import annotations

import re
from pathlib import Path

_QUERIES_DIR = Path(__file__).parent / "queries"

_query_cache: dict[str, str] = {}


def load_query(query_name: str) -> str:
    """Load a GraphQL query, appending any named fragments it references.

    A query may share a node selection by spreading a fragment (``...IssueFields``);
    the fragment lives once in ``queries/fragments/<Name>.graphql`` and is appended
    to the document here, so a base query and its ``_since`` variant never drift.
    """
    if query_name not in _query_cache:
        text = (_QUERIES_DIR / f"{query_name}.graphql").read_text(encoding="utf-8")
        for fragment in sorted(set(re.findall(r"\.\.\.(\w+)", text))):
            fragment_path = _QUERIES_DIR / "fragments" / f"{fragment}.graphql"
            if fragment_path.exists():
                text += "\n" + fragment_path.read_text(encoding="utf-8")
        _query_cache[query_name] = text
    return _query_cache[query_name]
