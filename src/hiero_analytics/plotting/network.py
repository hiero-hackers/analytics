"""Force-directed bubble network of repositories linked by shared members."""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
from matplotlib.patches import Patch

from hiero_analytics.analysis.repo_categories import CATEGORY_ORDER, categorize_repo
from hiero_analytics.config.charts import (
    MUTED_TEXT_COLOR,
    REPO_CATEGORY_COLORS,
    TITLE_COLOR,
)

from .style import apply_style

# Lower DPI than the bar/line charts: a large force layout would be huge at 300.
_NETWORK_DPI = 150
_OTHER_COLOR = REPO_CATEGORY_COLORS["Other"]


def _short(repo: str) -> str:
    """Shorten a repo name for labelling by dropping the common ``hiero-`` prefix."""
    return repo[len("hiero-"):] if repo.startswith("hiero-") else repo


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


def render_comembership_network(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    output_path: Path,
    *,
    title: str,
    member_label: str,
    seed: int = 42,
) -> bool:
    """Render a repo co-membership network to a PNG.

    Bubbles are repositories sized by ``active_members``; links are drawn for repo
    pairs in ``edges`` (width/opacity scaled by ``shared``). Node colour is the
    repo's semantic category (with a legend). ``member_label`` (e.g. "maintainers")
    is used in the caption. The layout is seeded for reproducibility. Returns False
    (and writes nothing) if there are no nodes.
    """
    if nodes.empty:
        return False

    apply_style()
    graph = nx.Graph()
    for row in nodes.itertuples():
        graph.add_node(row.repo, active=int(row.active_members))
    for row in edges.itertuples():
        if row.repo_a in graph and row.repo_b in graph:
            graph.add_edge(row.repo_a, row.repo_b, weight=int(row.shared))

    categories = {node: categorize_repo(node) for node in graph.nodes()}
    node_colors = [REPO_CATEGORY_COLORS.get(categories[node], _OTHER_COLOR) for node in graph.nodes()]

    # Each connected component laid out on its own and packed into a grid (so separate
    # clusters sit side by side, not flung apart); isolated bubbles tuck below.
    fig, ax = plt.subplots(figsize=(16, 12))
    pos, isolated = _packed_layout(graph, seed)
    if isolated:
        if pos:
            xs = [p[0] for p in pos.values()]
            ys = [p[1] for p in pos.values()]
            x_min, x_max, y_min = min(xs), max(xs), min(ys)
        else:
            x_min, x_max, y_min = -1.0, 1.0, -1.0
        # Fixed bubble spacing (not span-based) so a single isolate doesn't get
        # flung far below; centre the row under the clusters, just beneath them.
        gap = 0.9
        cols = min(len(isolated), 8)
        row_width = (cols - 1) * gap
        x_centre = (x_min + x_max) / 2
        top = y_min - gap * 1.8
        for i, node in enumerate(isolated):
            row, col = divmod(i, cols)
            pos[node] = (x_centre - row_width / 2 + col * gap, top - row * gap)
        ax.text(
            x_centre, top + gap * 0.8, f"not linked — no shared {member_label}",
            ha="center", va="bottom", fontsize=9, color=MUTED_TEXT_COLOR,
        )

    if graph.number_of_edges():
        weights = [graph[u][v]["weight"] for u, v in graph.edges()]
        max_w = max(weights)
        nx.draw_networkx_edges(
            graph, pos, ax=ax,
            width=[0.4 + 2.6 * (w / max_w) for w in weights],
            edge_color="#9AA8B8",
            alpha=0.35,
        )

    # Area encodes active members but compressed (sqrt) so big bubbles don't swamp.
    actives = [graph.nodes[node]["active"] for node in graph.nodes()]
    nx.draw_networkx_nodes(
        graph, pos, ax=ax,
        node_size=[140 + 260 * math.sqrt(a) for a in actives],
        node_color=node_colors,
        edgecolors="white",
        linewidths=1.2,
        alpha=0.92,
    )
    nx.draw_networkx_labels(
        graph, pos, ax=ax,
        labels={node: _short(node) for node in graph.nodes()},
        font_size=7, font_color=TITLE_COLOR,
        bbox={"boxstyle": "round,pad=0.12", "fc": "white", "ec": "none", "alpha": 0.7},
    )

    # Legend sits *outside* the plot (top-right) so it can never hide a bubble;
    # bbox_inches="tight" on save keeps it in frame.
    present = [c for c in CATEGORY_ORDER if c in set(categories.values())]
    handles = [Patch(facecolor=REPO_CATEGORY_COLORS[c], edgecolor="white", label=c) for c in present]
    legend = ax.legend(
        handles=handles, title="Repository type", loc="upper left", bbox_to_anchor=(1.01, 1.0),
        frameon=True, fontsize=9, title_fontsize=10, borderpad=0.8, labelspacing=0.5,
    )
    legend.get_frame().set_alpha(0.9)

    ax.set_title(title)
    ax.text(
        0.5, -0.02,
        f"Bubble size = active {member_label} · link width = shared {member_label} · colour = repository type",
        transform=ax.transAxes, ha="center", va="top", fontsize=10, color=MUTED_TEXT_COLOR,
    )
    ax.axis("off")
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=_NETWORK_DPI, bbox_inches="tight")
    plt.close(fig)
    return True
