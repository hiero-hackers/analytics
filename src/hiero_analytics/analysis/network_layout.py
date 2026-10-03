"""Layout of the repository co-membership network, as node and edge tables.

Repositories are nodes (sized by active members) and shared members are
weighted edges. Each connected component is laid out on its own with a seeded
spring layout and the components are packed into a grid, so separate clusters
sit side by side instead of being flung to the corners; isolated repositories
are tucked into rows beneath. The resulting ``x``/``y`` are what the dashboard's
interactive network draws, so the layout is computed once here and shipped as
data rather than recomputed in the browser.
"""

from __future__ import annotations

import math

import networkx as nx
import pandas as pd

from hiero_analytics.domain.repo_categories import categorize_repo


def _packed_layout(graph: nx.Graph, seed: int) -> tuple[dict, list]:
    """Lay out each connected component on its own, then pack them into a grid.

    spring_layout on a disconnected graph flings components to far corners (huge empty
    middle). Instead, lay out each component alone and normalize it to fill a radius
    that grows with its size — so separate clusters sit side by side and a tight clique
    is blown up to a readable size rather than squashed into a ball. Returns
    ``(pos, isolated_nodes)`` where isolated (degree-0) nodes are left for the caller
    to tuck away.
    """
    isolated = [node for node in graph.nodes() if graph.degree(node) == 0]
    components = sorted(
        (list(c) for c in nx.connected_components(graph) if len(c) > 1),
        key=len,
        reverse=True,
    )
    if not components:
        return {}, isolated

    radii = [0.6 + 0.5 * math.sqrt(len(comp)) for comp in components]
    spacing = 2.4 * max(radii)
    cols = max(1, math.ceil(math.sqrt(len(components))))

    pos: dict = {}
    for i, (comp, radius) in enumerate(zip(components, radii, strict=True)):
        # weight=None lays out by topology, so high-overlap cliques spread out rather
        # than collapsing; edge *widths* still use weight when drawn.
        local = nx.spring_layout(graph.subgraph(comp), seed=seed, k=1.4, iterations=500)
        xs = [p[0] for p in local.values()]
        ys = [p[1] for p in local.values()]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        half = max(max(xs) - min(xs), max(ys) - min(ys), 1e-6) / 2
        row, col = divmod(i, cols)
        ox, oy = col * spacing, -row * spacing
        for node, (x, y) in local.items():
            pos[node] = (ox + (x - cx) / half * radius, oy + (y - cy) / half * radius)
    return pos, isolated


def _graph(nodes: pd.DataFrame, edges: pd.DataFrame) -> nx.Graph:
    """Repositories as nodes (with active members), shared members as weighted edges."""
    graph = nx.Graph()
    for row in nodes.itertuples():
        graph.add_node(row.repo, active=int(row.active_members))
    for row in edges.itertuples():
        if row.repo_a in graph and row.repo_b in graph:
            graph.add_edge(row.repo_a, row.repo_b, weight=int(row.shared))
    return graph


# Isolated bubbles sit in rows of up to eight, at a fixed spacing, under the clusters.
_ISOLATE_GAP = 0.9
_ISOLATE_COLS = 8


def network_layout(graph: nx.Graph, seed: int = 42) -> tuple[dict, list, tuple[float, float] | None]:
    """Node positions and the "not linked" caption point, for the interactive network.

    Returns ``(pos, isolated, caption)``; ``caption`` is None when every node is linked.
    """
    pos, isolated = _packed_layout(graph, seed)
    if not isolated:
        return pos, isolated, None
    if pos:
        xs = [p[0] for p in pos.values()]
        ys = [p[1] for p in pos.values()]
        x_min, x_max, y_min = min(xs), max(xs), min(ys)
    else:
        x_min, x_max, y_min = -1.0, 1.0, -1.0
    # Fixed bubble spacing (not span-based) so a single isolate doesn't get
    # flung far below; centre the row under the clusters, just beneath them.
    cols = min(len(isolated), _ISOLATE_COLS)
    row_width = (cols - 1) * _ISOLATE_GAP
    x_centre = (x_min + x_max) / 2
    top = y_min - _ISOLATE_GAP * 1.8
    for i, node in enumerate(isolated):
        row, col = divmod(i, cols)
        pos[node] = (x_centre - row_width / 2 + col * _ISOLATE_GAP, top - row * _ISOLATE_GAP)
    return pos, isolated, (x_centre, top + _ISOLATE_GAP * 0.8)


def network_tables(nodes: pd.DataFrame, edges: pd.DataFrame, seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The drawn network as node and edge tables, with each node's ``category`` and laid-out ``x``/``y``."""
    graph = _graph(nodes, edges)
    pos, _isolated, _caption = network_layout(graph, seed)
    node_table = nodes[["repo", "active_members", "total_members"]].copy()
    node_table["category"] = node_table["repo"].map(categorize_repo)
    node_table["x"] = node_table["repo"].map(lambda repo: round(pos[repo][0], 4))
    node_table["y"] = node_table["repo"].map(lambda repo: round(pos[repo][1], 4))
    edge_table = edges[edges["repo_a"].isin(graph) & edges["repo_b"].isin(graph)][["repo_a", "repo_b", "shared"]]
    return node_table.reset_index(drop=True), edge_table.reset_index(drop=True)
