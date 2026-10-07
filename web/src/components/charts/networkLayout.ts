/**
 * Relaxes the exported spring layout with a small force simulation (springs,
 * label-aware collisions, wide gravity) so no bubble or label hides another.
 * Deterministic: it starts from the exported positions and uses no randomness.
 */

interface LayoutNode {
  id: string;
  x: number;
  y: number;
  /** Collision radius: the bubble plus the room its label needs. */
  radius: number;
}

interface LayoutEdge {
  source: string;
  target: string;
}

const TICKS = 320;
const ALPHA_DECAY = 1 - 0.001 ** (1 / TICKS);
const VELOCITY_DECAY = 0.55;
/** Horizontal gravity is weaker than vertical, so the result is wider than tall. */
const GRAVITY = { x: 0.02, y: 0.09 };
/** Slack between two linked bubbles' collision edges, before the spring pulls. */
const LINK_GAP = 24;

export function relaxLayout(
  nodes: LayoutNode[],
  edges: LayoutEdge[],
): Map<string, { x: number; y: number }> {
  const index = new Map(nodes.map((node, i) => [node.id, i]));
  const n = nodes.length;
  // Centre the seed layout so gravity pulls towards its middle.
  const mx = nodes.reduce((sum, node) => sum + node.x, 0) / Math.max(1, n);
  const my = nodes.reduce((sum, node) => sum + node.y, 0) / Math.max(1, n);
  const x = nodes.map((node) => node.x - mx);
  const y = nodes.map((node) => node.y - my);
  const vx = new Array<number>(n).fill(0);
  const vy = new Array<number>(n).fill(0);
  const r = nodes.map((node) => node.radius);

  const links = edges
    .map((edge) => [index.get(edge.source), index.get(edge.target)] as const)
    .filter(
      (pair): pair is readonly [number, number] => pair[0] !== undefined && pair[1] !== undefined,
    );
  const degree = new Array<number>(n).fill(0);
  for (const [a, b] of links) {
    degree[a] += 1;
    degree[b] += 1;
  }

  let alpha = 1;
  for (let tick = 0; tick < TICKS; tick += 1) {
    alpha += (0 - alpha) * ALPHA_DECAY;

    // Springs: towards touching-plus-a-gap, weaker for hubs (d3-force's rule).
    for (const [a, b] of links) {
      let dx = x[b] + vx[b] - x[a] - vx[a];
      let dy = y[b] + vy[b] - y[a] - vy[a];
      const length = Math.hypot(dx, dy) || 1e-6;
      const target = r[a] + r[b] + LINK_GAP;
      const strength = 1 / Math.min(degree[a], degree[b]);
      const k = ((length - target) / length) * alpha * strength;
      dx *= k;
      dy *= k;
      const bias = degree[a] / (degree[a] + degree[b]);
      vx[b] -= dx * bias;
      vy[b] -= dy * bias;
      vx[a] += dx * (1 - bias);
      vy[a] += dy * (1 - bias);
    }

    for (let i = 0; i < n; i += 1) {
      vx[i] -= x[i] * GRAVITY.x * alpha;
      vy[i] -= y[i] * GRAVITY.y * alpha;
    }

    // Collisions on the predicted positions; the larger node moves less.
    for (let i = 0; i < n; i += 1) {
      for (let j = i + 1; j < n; j += 1) {
        let dx = x[j] + vx[j] - x[i] - vx[i];
        let dy = y[j] + vy[j] - y[i] - vy[i];
        const min = r[i] + r[j];
        let distance = Math.hypot(dx, dy);
        if (distance >= min) continue;
        if (distance < 1e-6) {
          // Coincident seeds: separate along a fixed, index-derived direction.
          dx = Math.cos(i + j);
          dy = Math.sin(i + j);
          distance = 1;
        }
        const push = ((min - distance) / distance) * 0.7;
        const share = (r[j] * r[j]) / (r[i] * r[i] + r[j] * r[j]);
        vx[i] -= dx * push * share;
        vy[i] -= dy * push * share;
        vx[j] += dx * push * (1 - share);
        vy[j] += dy * push * (1 - share);
      }
    }

    for (let i = 0; i < n; i += 1) {
      vx[i] *= 1 - VELOCITY_DECAY;
      vy[i] *= 1 - VELOCITY_DECAY;
      x[i] += vx[i];
      y[i] += vy[i];
    }
  }
  return new Map(nodes.map((node, i) => [node.id, { x: x[i], y: y[i] }]));
}

/** Link-strength thresholds: every link, then the median, upper quartile and top decile of shared members. */
export function strengthSteps(shared: number[]): number[] {
  const sorted = [...shared].sort((a, b) => a - b);
  if (!sorted.length) return [];
  const at = (q: number) => sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))];
  return [...new Set([sorted[0], at(0.5), at(0.75), at(0.9)])];
}
