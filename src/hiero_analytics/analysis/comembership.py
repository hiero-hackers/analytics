"""Co-membership networks: repositories linked by people they share.

A bipartite (person × repo) relationship projected onto repositories. Each repo is
a node sized by its *active* members of some group (maintainers, committers, triage,
or general contributors); two repos are linked when they share members of that group
(edge weight = how many). This surfaces clusters of repos worked on by the same
people. Descriptive only — no ranking.
"""

from __future__ import annotations

import itertools
from collections import Counter

import pandas as pd

_NODE_COLUMNS = ["repo", "active_members", "total_members"]
_EDGE_COLUMNS = ["repo_a", "repo_b", "shared"]


def role_membership(coverage: pd.DataFrame, role: str) -> pd.DataFrame:
    """Membership table ``[repo, user, active]`` for one governance role.

    Drawn from the combined ``role_coverage_all`` table; ``active`` is the repo's
    recency status (status == "active").
    """
    cols = ["repo", "user", "active"]
    if coverage.empty or "granted_role" not in coverage:
        return pd.DataFrame(columns=cols)
    rows = coverage[coverage["granted_role"] == role][["repo", "user", "status"]].copy()
    rows["active"] = rows["status"] == "active"
    return rows[cols]


def build_comembership_network(
    membership: pd.DataFrame,
    *,
    min_shared: int = 1,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build repo nodes and shared-member edges from a membership table.

    Args:
        membership: Long table with columns ``repo``, ``user``, ``active`` (bool).
            Repo names may be ``owner/name``; only the bare name is kept.
        min_shared: Minimum shared members for an edge to be kept (raise to thin a
            dense group into something readable).

    Returns:
        ``(nodes, edges)``. ``nodes`` has one row per repo with at least one member:
        ``repo``, ``active_members``, ``total_members``. ``edges`` has ``repo_a``,
        ``repo_b``, ``shared`` for repo pairs sharing at least ``min_shared`` members
        (edges use all members, active or not, so latent structure shows even when
        the group is quiet).
    """
    empty = (pd.DataFrame(columns=_NODE_COLUMNS), pd.DataFrame(columns=_EDGE_COLUMNS))
    if membership.empty or "repo" not in membership or "user" not in membership:
        return empty

    rows = membership.copy()
    rows["repo"] = rows["repo"].astype(str).str.split("/").str[-1]
    rows["user"] = rows["user"].astype(str).str.lower()

    total = rows.groupby("repo")["user"].nunique()
    active = rows[rows["active"].astype(bool)].groupby("repo")["user"].nunique()
    nodes = pd.DataFrame({"repo": total.index, "total_members": total.to_numpy()})
    nodes["active_members"] = nodes["repo"].map(active).fillna(0).astype(int)
    nodes = nodes[_NODE_COLUMNS].sort_values(
        ["active_members", "total_members"], ascending=False
    ).reset_index(drop=True)

    # Edge weight = number of members two repos have in common.
    repos_per_user = rows.groupby("user")["repo"].apply(lambda s: sorted(set(s)))
    shared: Counter = Counter()
    for repos in repos_per_user:
        for repo_a, repo_b in itertools.combinations(repos, 2):
            shared[(repo_a, repo_b)] += 1

    edges = pd.DataFrame(
        [(a, b, count) for (a, b), count in shared.items() if count >= min_shared],
        columns=_EDGE_COLUMNS,
    ).sort_values("shared", ascending=False).reset_index(drop=True)
    return nodes, edges
