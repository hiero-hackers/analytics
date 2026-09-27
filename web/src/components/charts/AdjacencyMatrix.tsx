/**
 * The network as a repository × repository matrix, so every pair of a dense
 * graph gets its own cell. Rows are grouped by type, then ordered by total shared
 * members; shading is logarithmic because shared counts are heavily skewed.
 */

import { useMemo, useState } from 'react';
import type { ChartSeries, NetworkNode } from '../../api';
import { integer, shortRepo as short } from './format';

const CELL = 14;
const LEFT = 176;
/** Room for the rotated column names: up (TOP) and out past the last column (RIGHT). */
const TOP = 156;
const RIGHT = 112;
const STEPS = 5;

const step = (value: number, max: number) =>
  value <= 0 ? 0 : Math.max(1, Math.ceil((STEPS * Math.log1p(value)) / Math.log1p(max)));

export function AdjacencyMatrix({
  nodes,
  edges,
  categories,
  member,
  selected,
  onSelect,
}: {
  nodes: NetworkNode[];
  edges: { source: string; target: string; shared: number }[];
  categories: ChartSeries[];
  member: string;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const [hover, setHover] = useState<{ row: number; col: number } | null>(null);

  const { order, shared, max, bands } = useMemo(() => {
    const pair = new Map<string, number>();
    const strength = new Map<string, number>(nodes.map((node) => [node.id, 0]));
    for (const edge of edges) {
      pair.set(`${edge.source}\u0000${edge.target}`, edge.shared);
      pair.set(`${edge.target}\u0000${edge.source}`, edge.shared);
      strength.set(edge.source, (strength.get(edge.source) ?? 0) + edge.shared);
      strength.set(edge.target, (strength.get(edge.target) ?? 0) + edge.shared);
    }
    const rank = new Map(categories.map((category, i) => [category.key, i]));
    const sorted = [...nodes].sort(
      (a, b) =>
        (rank.get(a.category) ?? 99) - (rank.get(b.category) ?? 99) ||
        strength.get(b.id)! - strength.get(a.id)! ||
        a.id.localeCompare(b.id),
    );
    // Where one repository type ends and the next begins, for the group rules.
    const breaks = sorted.flatMap((node, i) =>
      i && node.category !== sorted[i - 1].category ? [i] : [],
    );
    return {
      order: sorted,
      shared: (a: string, b: string) => pair.get(`${a}\u0000${b}`) ?? 0,
      max: Math.max(1, ...edges.map((edge) => edge.shared)),
      bands: breaks,
    };
  }, [nodes, edges, categories]);

  const colors = new Map(categories.map((category) => [category.key, category.color]));
  const n = order.length;
  const width = LEFT + n * CELL + RIGHT;
  const height = TOP + n * CELL + 8;
  const selectedIndex = selected ? order.findIndex((node) => node.id === selected) : -1;

  // Each shade's exact integer range, for the legend.
  const legend = Array.from({ length: STEPS }, (_, i) => {
    const values = Array.from({ length: max }, (_, v) => v + 1).filter(
      (v) => step(v, max) === i + 1,
    );
    return values.length ? [values[0], values.at(-1)!] : null;
  });

  const readout = hover
    ? (() => {
        const a = order[hover.row];
        const b = order[hover.col];
        if (a.id === b.id)
          return `${a.id}: ${integer.format(a.active)} active of ${integer.format(a.total)} ${member}`;
        const value = shared(a.id, b.id);
        return `${short(a.id)} × ${short(b.id)}: ${value ? `${integer.format(value)} shared ${member}` : 'no link at this threshold'}`;
      })()
    : `Hover a cell to read how many ${member} two repositories share.`;

  const label = (node: NetworkNode, index: number, axis: 'row' | 'col') => {
    const active =
      index === selectedIndex || (hover && (axis === 'row' ? hover.row : hover.col) === index);
    return (
      <text
        fontSize={11}
        fontWeight={active ? 600 : 400}
        fill={active ? 'var(--ink)' : 'var(--muted)'}
        dominantBaseline="middle"
        textAnchor={axis === 'row' ? 'end' : 'start'}
      >
        {short(node.id)}
      </text>
    );
  };

  return (
    <div className="space-y-2">
      <p className="min-h-5 text-xs text-foreground" aria-live="polite">
        {readout}
      </p>
      <div className="overflow-auto rounded-lg border bg-card">
        {/* Scrolls rather than shrinks when narrow; grows up to 1.5× in a wide card. */}
        <svg
          viewBox={`0 0 ${width} ${height}`}
          style={{ minWidth: width, maxWidth: width * 1.5 }}
          role="group"
          aria-label={`Shared ${member} between every pair of ${n} repositories, grouped by type. Use Data for the full list.`}
          className="mx-auto block w-full"
          onPointerLeave={() => setHover(null)}
        >
          {order.map((node, i) => (
            <g
              key={`row-${node.id}`}
              role="button"
              tabIndex={0}
              aria-pressed={selected === node.id}
              aria-label={`Select ${node.id}`}
              className="cursor-pointer outline-none focus-visible:[&_text]:underline"
              transform={`translate(${LEFT - 8} ${TOP + i * CELL + CELL / 2})`}
              onClick={() => onSelect(node.id)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onSelect(node.id);
                }
              }}
            >
              <circle cx={4} cy={0} r={3.5} fill={colors.get(node.category)} />
              <g transform="translate(-4 0)">{label(node, i, 'row')}</g>
            </g>
          ))}
          {order.map((node, i) => (
            <g
              key={`col-${node.id}`}
              transform={`translate(${LEFT + i * CELL + CELL / 2} ${TOP - 8}) rotate(-55)`}
              aria-hidden="true"
            >
              <circle cx={0} cy={0} r={3.5} fill={colors.get(node.category)} />
              <g transform="translate(7 0)">{label(node, i, 'col')}</g>
            </g>
          ))}

          {/* Hover and selection bands come first so they sit behind the cells. */}
          {[hover?.row, selectedIndex >= 0 ? selectedIndex : undefined].map(
            (index, k) =>
              index !== undefined && (
                <rect
                  key={`rowband-${k}`}
                  x={LEFT}
                  y={TOP + index * CELL}
                  width={n * CELL}
                  height={CELL}
                  fill="var(--link)"
                  opacity={0.08}
                />
              ),
          )}
          {[hover?.col, selectedIndex >= 0 ? selectedIndex : undefined].map(
            (index, k) =>
              index !== undefined && (
                <rect
                  key={`colband-${k}`}
                  x={LEFT + index * CELL}
                  y={TOP}
                  width={CELL}
                  height={n * CELL}
                  fill="var(--link)"
                  opacity={0.08}
                />
              ),
          )}

          {order.map((a, row) =>
            order.map((b, col) => {
              const diagonal = row === col;
              const shade = diagonal ? 0 : step(shared(a.id, b.id), max);
              return (
                <rect
                  key={`${a.id}|${b.id}`}
                  x={LEFT + col * CELL + 1}
                  y={TOP + row * CELL + 1}
                  width={CELL - 2}
                  height={CELL - 2}
                  rx={2}
                  fill={
                    diagonal
                      ? (colors.get(a.category) ?? 'var(--edge-strong)')
                      : shade
                        ? `var(--heat-${shade})`
                        : 'var(--raise)'
                  }
                  fillOpacity={diagonal ? 0.35 : 1}
                  onPointerEnter={() => setHover({ row, col })}
                />
              );
            }),
          )}

          {bands.map((index) => (
            <g key={`band-${index}`} stroke="var(--edge-strong)" strokeWidth={1}>
              <line
                x1={LEFT}
                x2={LEFT + n * CELL}
                y1={TOP + index * CELL}
                y2={TOP + index * CELL}
              />
              <line
                y1={TOP}
                y2={TOP + n * CELL}
                x1={LEFT + index * CELL}
                x2={LEFT + index * CELL}
              />
            </g>
          ))}
        </svg>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span>Shared {member}:</span>
        <span className="inline-flex items-center gap-1.5">
          <i className="inline-block size-3 rounded-sm bg-raise" /> none
        </span>
        {legend.map(
          (range, i) =>
            range && (
              <span key={i} className="inline-flex items-center gap-1.5">
                <i
                  className="inline-block size-3 rounded-sm"
                  style={{ backgroundColor: `var(--heat-${i + 1})` }}
                />
                <span className="tabular-nums">
                  {range[0] === range[1] ? range[0] : `${range[0]}–${range[1]}`}
                </span>
              </span>
            ),
        )}
      </div>
    </div>
  );
}
