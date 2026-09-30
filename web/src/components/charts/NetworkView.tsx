/**
 * The `network` kind: repositories linked by shared members, sized like
 * plotting/network.py (bubble area ~ √active members, link width ~ shared).
 * Wheel zoom needs Ctrl/⌘ so a plain wheel still scrolls the page.
 */

import { useCallback, useMemo, useRef, useState, type PointerEvent } from 'react';
import { MinusIcon, PlusIcon, RotateCcwIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { ColumnSpec, NetworkDocument, Row } from '../../api';
import { matches as focusMatches, useFocus } from '../../focus';
import { useUrlParam } from '../../urlState';
import { VariantTabs } from '../VariantTabs';
import { EntityLink } from '../EntityLink';
import { AdjacencyMatrix } from './AdjacencyMatrix';
import { ChartShell, TABLE_CONTAINER, type SheetBox, type ViewProps } from './ChartShell';
import { integer, rangeText, shortRepo as short, windowText } from './format';
import { relaxLayout, strengthSteps } from './networkLayout';

/** SVG units per layout unit: roughly plotting/network.py's points per unit at 16 inches wide. */
const UNIT = 110;
const PAD = 48;
const MIN_ZOOM = 0.5;
const MAX_ZOOM = 4;

type Viewport = { zoom: number; x: number; y: number };
const zoomed = (view: Viewport, factor: number): Viewport => ({
  ...view,
  zoom: Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, view.zoom * factor)),
});

/** plotting/network.py's marker area (140 + 260·√active pt²) as a radius, enlarged for card width. */
const radius = (active: number) => 1.6 * Math.sqrt((140 + 260 * Math.sqrt(active)) / Math.PI);
/** Room a node claims: its bubble with the label below it, or the label's half-width if wider. */
const LABEL_BELOW = 17;
const labelHalf = (id: string) => short(id).length * 3.6 + 4;
const claim = (id: string, r: number) => Math.max(r + LABEL_BELOW, labelHalf(id)) + 3;

export function NetworkView({ data, title, period, provenance }: ViewProps<NetworkDocument>) {
  const [query, setQuery] = useUrlParam(`${data.id}.q`);
  // The selected repository is the dashboard focus, so it filters every repository table too.
  const [dashboardFocus, setFocus] = useFocus();
  const selected =
    data.nodes.find((node) => focusMatches(dashboardFocus, 'repo', node.id))?.id ?? null;
  const setSelected = (id: string | null) => setFocus(id ? { dimension: 'repo', value: id } : null);
  const [focused, setFocused] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [mode, setMode] = useUrlParam(`${data.id}.mode`, 'graph');
  const matrix = mode === 'matrix';
  const steps = useMemo(() => strengthSteps(data.edges.map((edge) => edge.shared)), [data.edges]);
  const [linkedMin, setMin] = useUrlParam(`${data.id}.min`, String(steps[0] ?? 0));
  // A stale link (a threshold this document no longer offers) shows every link.
  const minShared = steps.includes(Number(linkedMin)) ? Number(linkedMin) : (steps[0] ?? 0);
  const edges = data.edges.filter((edge) => edge.shared >= minShared);
  const [view, setView] = useState<Viewport>({ zoom: 1, x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const member = data.member_label;

  const colors = useMemo(
    () => new Map(data.categories.map((category) => [category.key, category.color])),
    [data.categories],
  );
  const neighbours = useMemo(() => {
    const map = new Map<string, { id: string; shared: number }[]>(
      data.nodes.map((node) => [node.id, []]),
    );
    for (const edge of data.edges.filter((edge) => edge.shared >= minShared)) {
      map.get(edge.source)?.push({ id: edge.target, shared: edge.shared });
      map.get(edge.target)?.push({ id: edge.source, shared: edge.shared });
    }
    for (const list of map.values())
      list.sort((a, b) => b.shared - a.shared || a.id.localeCompare(b.id));
    return map;
  }, [data, minShared]);

  // The layout uses every link, so thinning the web never moves a bubble.
  const { positions, bounds, isolated } = useMemo(() => {
    const linked = new Set(data.edges.flatMap((edge) => [edge.source, edge.target]));
    const connected = data.nodes.filter((node) => linked.has(node.id));
    const relaxed = relaxLayout(
      connected.map((node) => ({
        id: node.id,
        // SVG y runs down; the layout's runs up.
        x: node.x * UNIT,
        y: -node.y * UNIT,
        radius: claim(node.id, radius(node.active)),
      })),
      data.edges,
    );
    const alone = data.nodes.filter((node) => !linked.has(node.id));
    const placed = new Map<string, { cx: number; cy: number }>();
    for (const [id, point] of relaxed) placed.set(id, { cx: point.x, cy: point.y });
    // Unlinked repositories sit in a labelled row beneath the web.
    const claims = alone.map((node) => claim(node.id, radius(node.active)));
    const bottom = Math.max(
      0,
      ...connected.map((node) => placed.get(node.id)!.cy + claim(node.id, radius(node.active))),
    );
    const rowWidth = claims.reduce((sum, c) => sum + 2 * c, 0);
    let cursor = -rowWidth / 2;
    alone.forEach((node, i) => {
      placed.set(node.id, { cx: cursor + claims[i], cy: bottom + 56 + radius(node.active) });
      cursor += 2 * claims[i];
    });
    const extents = data.nodes.map((node) => {
      const { cx, cy } = placed.get(node.id)!;
      const r = radius(node.active);
      const half = Math.max(r, labelHalf(node.id));
      return { left: cx - half, right: cx + half, top: cy - r, bottom: cy + r + LABEL_BELOW + 4 };
    });
    const minX = Math.min(...extents.map((e) => e.left)) - PAD;
    const minY = Math.min(...extents.map((e) => e.top)) - PAD;
    const maxX = Math.max(...extents.map((e) => e.right)) + PAD;
    const maxY = Math.max(...extents.map((e) => e.bottom)) + PAD;
    for (const point of placed.values()) {
      point.cx -= minX;
      point.cy -= minY;
    }
    return {
      positions: placed,
      bounds: { width: maxX - minX, height: maxY - minY },
      isolated: alone,
    };
  }, [data.nodes, data.edges]);
  const maxShared = Math.max(1, ...data.edges.map((edge) => edge.shared));

  const needle = query.trim().toLowerCase();
  const matches = new Set(
    needle
      ? data.nodes.filter((node) => node.id.toLowerCase().includes(needle)).map((n) => n.id)
      : [],
  );
  const focus = selected ?? (matches.size === 1 ? [...matches][0] : null);
  // Hover previews a neighbourhood without changing the selection or the table.
  const shown = hovered ?? focus;
  const lit = shown ? new Set([shown, ...(neighbours.get(shown) ?? []).map((n) => n.id)]) : null;
  const dimmed = (id: string) => (lit ? !lit.has(id) : needle ? !matches.has(id) : false);

  const zoomBy = (factor: number) => setView((current) => zoomed(current, factor));
  // React registers `onWheel` as a passive listener, where preventDefault is a
  // no-op and Ctrl+wheel (and trackpad pinch) would zoom the page too, so the
  // wheel listener is attached natively. The graph renders inline and in the
  // lightbox; each copy's ref wires its own listener and removes it on unmount.
  const attachSvg = useCallback((svg: SVGSVGElement | null) => {
    svgRef.current = svg;
    if (!svg) return;
    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      setView((current) => zoomed(current, event.deltaY < 0 ? 1.15 : 1 / 1.15));
    };
    svg.addEventListener('wheel', onWheel, { passive: false });
    return () => svg.removeEventListener('wheel', onWheel);
  }, []);
  const toSvg = (dx: number) => {
    const width = svgRef.current?.getBoundingClientRect().width || bounds.width;
    return (dx * bounds.width) / width;
  };
  const onPointerDown = (event: PointerEvent<SVGSVGElement>) => {
    if ((event.target as Element).closest('[data-node]')) return;
    drag.current = { x: event.clientX, y: event.clientY, ox: view.x, oy: view.y };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };
  const onPointerMove = (event: PointerEvent<SVGSVGElement>) => {
    const start = drag.current;
    if (!start) return;
    setView((current) => ({
      ...current,
      x: start.ox + toSvg(event.clientX - start.x) / current.zoom,
      y: start.oy + toSvg(event.clientY - start.y) / current.zoom,
    }));
  };

  const scope = focus ? new Set([focus, ...(neighbours.get(focus) ?? []).map((n) => n.id)]) : null;
  const inScope = (id: string) => (scope ? scope.has(id) : needle ? matches.has(id) : true);
  const tableRows: Row[] = data.nodes
    .filter((node) => inScope(node.id))
    .map((node) => {
      const links = neighbours.get(node.id) ?? [];
      return {
        repo: node.id,
        category: node.category,
        active: node.active,
        total: node.total,
        links: links.length,
        linked: links.map((link) => `${link.id} (${link.shared})`).join('; '),
      };
    });
  const columns: ColumnSpec[] = [
    { key: 'repo', label: 'Repository' },
    { key: 'category', label: 'Type' },
    { key: 'active', label: `Active ${member}`, format: 'number' },
    { key: 'total', label: `All ${member}`, format: 'number' },
    { key: 'links', label: 'Linked repositories', format: 'number' },
    { key: 'linked', label: `Links (shared ${member})` },
  ];
  const select = (id: string) => setSelected(selected === id ? null : id);
  const cx = bounds.width / 2;
  const cy = bounds.height / 2;

  const toolbar = (
    <>
      <VariantTabs
        appearance="segmented"
        labels={['Graph', 'Matrix']}
        active={matrix ? 1 : 0}
        onSelect={(index) => setMode(index ? 'matrix' : 'graph')}
        ariaLabel={`${title} layout`}
      />
      {steps.length > 1 && (
        <VariantTabs
          appearance="segmented"
          labels={steps.map((step, i) => (i ? `≥ ${step} shared` : 'All links'))}
          active={steps.indexOf(minShared)}
          onSelect={(index) => setMin(String(steps[index]))}
          ariaLabel={`${title}: minimum shared ${member}`}
        />
      )}
      {minShared > (steps[0] ?? 0) && (
        // Printed as a filter instead.
        <span className="text-xs text-muted-foreground" aria-live="polite" data-sheet-hide>
          Showing {integer.format(edges.length)} of {integer.format(data.edges.length)} links
        </span>
      )}
    </>
  );

  const controls = (
    <div className="flex flex-wrap items-center gap-2">
      <Input
        className="h-8 max-w-xs"
        placeholder="Find a repository…"
        aria-label="Find a repository"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          if (selected) setSelected(null);
        }}
      />
      {selected && (
        <Button variant="outline" size="sm" onClick={() => setSelected(null)}>
          Clear focus
        </Button>
      )}
    </div>
  );

  const chart = (expanded: boolean, sheet?: SheetBox) => {
    const focusNode = focus ? data.nodes.find((node) => node.id === focus) : undefined;
    return (
      // On paper the graph (or matrix) takes the page's height left by its legend and focus.
      <div
        className={sheet ? 'flex flex-col gap-3' : 'space-y-3'}
        style={sheet ? { height: sheet.height } : undefined}
      >
        {matrix ? (
          <AdjacencyMatrix
            nodes={data.nodes}
            edges={edges}
            categories={data.categories}
            member={member}
            selected={focus}
            onSelect={select}
            fit={!!sheet}
          />
        ) : (
          <div
            className={`relative overflow-hidden rounded-lg border bg-card ${sheet ? 'flex min-h-0 flex-1' : ''}`}
          >
            {!sheet && (
              <div className="absolute top-2 right-2 z-10 flex gap-1">
                <Button
                  variant="outline"
                  size="icon"
                  aria-label="Zoom in"
                  onClick={() => zoomBy(1.25)}
                >
                  <PlusIcon />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  aria-label="Zoom out"
                  onClick={() => zoomBy(0.8)}
                >
                  <MinusIcon />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  aria-label="Reset view"
                  onClick={() => setView({ zoom: 1, x: 0, y: 0 })}
                >
                  <RotateCcwIcon />
                </Button>
              </div>
            )}
            <svg
              // The printed copy neither zooms nor pans; the reader's own zoom still applies.
              ref={sheet ? undefined : attachSvg}
              role="group"
              aria-label={`${title}: ${data.nodes.length} repositories, ${edges.length} links. Tab to a repository and press Enter to show its links.`}
              viewBox={`0 0 ${bounds.width} ${bounds.height}`}
              className={`block w-full cursor-grab touch-none select-none active:cursor-grabbing ${sheet ? 'h-full min-h-0' : expanded ? 'max-h-[74vh]' : 'max-h-[640px]'}`}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={() => (drag.current = null)}
              onPointerLeave={() => (drag.current = null)}
              onKeyDown={(event) => event.key === 'Escape' && setSelected(null)}
            >
              <g
                transform={`translate(${cx} ${cy}) scale(${view.zoom}) translate(${view.x - cx} ${view.y - cy})`}
              >
                {edges.map((edge) => {
                  const a = positions.get(edge.source)!;
                  const b = positions.get(edge.target)!;
                  const on = shown ? edge.source === shown || edge.target === shown : false;
                  return (
                    <line
                      key={`${edge.source}|${edge.target}`}
                      x1={a.cx}
                      y1={a.cy}
                      x2={b.cx}
                      y2={b.cy}
                      stroke={on ? 'var(--ink)' : 'var(--edge-strong)'}
                      strokeOpacity={on ? 0.8 : shown ? 0.08 : 0.45}
                      strokeWidth={0.4 + 2.6 * (edge.shared / maxShared)}
                    />
                  );
                })}
                {isolated.length > 0 && (
                  <text
                    x={
                      isolated.reduce((sum, node) => sum + positions.get(node.id)!.cx, 0) /
                      isolated.length
                    }
                    y={Math.min(...isolated.map((node) => positions.get(node.id)!.cy)) - 34}
                    textAnchor="middle"
                    fontSize={11}
                    fill="var(--soft)"
                  >
                    not linked — no shared {member}
                  </text>
                )}
                {data.nodes.map((node) => {
                  const { cx: x, cy: y } = positions.get(node.id)!;
                  const r = radius(node.active);
                  const links = neighbours.get(node.id)?.length ?? 0;
                  const faded = dimmed(node.id);
                  const ring =
                    node.id === shown ||
                    node.id === focus ||
                    node.id === focused ||
                    matches.has(node.id);
                  return (
                    <g
                      key={node.id}
                      data-node={node.id}
                      role="button"
                      tabIndex={0}
                      aria-pressed={selected === node.id}
                      aria-label={`${node.id}, ${node.category}: ${node.active} active ${member}, linked to ${links} ${links === 1 ? 'repository' : 'repositories'}`}
                      className="cursor-pointer outline-none"
                      opacity={faded ? 0.2 : 1}
                      onClick={() => select(node.id)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          select(node.id);
                        }
                      }}
                      onFocus={() => setFocused(node.id)}
                      onBlur={() => setFocused(null)}
                      onPointerEnter={() => setHovered(node.id)}
                      onPointerLeave={() => setHovered(null)}
                    >
                      <title>{`${node.id} — ${node.active} active / ${node.total} ${member}, ${links} links`}</title>
                      <circle
                        cx={x}
                        cy={y}
                        r={r}
                        fill={colors.get(node.category) ?? 'var(--chart-general)'}
                        fillOpacity={0.92}
                        stroke={ring ? 'var(--ink)' : 'var(--surface)'}
                        strokeWidth={ring ? 2.5 : 1.2}
                      />
                      <text
                        x={x}
                        y={y + r + 13}
                        textAnchor="middle"
                        fontSize={12}
                        fill="var(--ink)"
                        paintOrder="stroke"
                        stroke="var(--surface)"
                        strokeWidth={3}
                      >
                        {short(node.id)}
                      </text>
                    </g>
                  );
                })}
              </g>
            </svg>
          </div>
        )}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>Repository type:</span>
          {data.categories.map((category) => (
            <span key={category.key} className="inline-flex items-center gap-1.5">
              <i
                className="inline-block size-3 rounded-full"
                style={{ backgroundColor: category.color }}
              />
              {category.label}
            </span>
          ))}
          <span>
            {matrix
              ? `· Stronger shade = more shared ${member} · diagonal = the repository itself`
              : `· Bubble size = active ${member} · link width = shared ${member}`}
          </span>
        </div>
        {focusNode ? (
          <div className="rounded-lg border p-3 text-sm" aria-live="polite">
            <p className="font-semibold">
              <EntityLink kind="repo" name={focusNode.id} />{' '}
              <span className="font-normal text-muted-foreground">
                · {focusNode.category} · {integer.format(focusNode.active)} active of{' '}
                {integer.format(focusNode.total)} {member}
              </span>
            </p>
            {neighbours.get(focusNode.id)?.length ? (
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {neighbours.get(focusNode.id)!.map((link) => (
                  <li key={link.id}>
                    <Button
                      data-print-keep
                      variant="outline"
                      size="sm"
                      onClick={() => setSelected(link.id)}
                    >
                      {short(link.id)}
                      <span className="text-muted-foreground tabular-nums">
                        {integer.format(link.shared)} shared
                      </span>
                    </Button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-muted-foreground">
                No shared {member} with another repository.
              </p>
            )}
          </div>
        ) : (
          !sheet && (
            <p className="text-xs text-muted-foreground">
              {matrix
                ? 'Hover a cell to read a pair; select a repository name to show its links.'
                : 'Hover, select or search a repository to show its links. Drag to pan; zoom with the buttons or Ctrl/⌘ + scroll.'}
            </p>
          )
        )}
      </div>
    );
  };

  const table = (
    <Table containerClassName={TABLE_CONTAINER}>
      <TableHeader className="sticky top-0 bg-muted">
        <TableRow>
          {columns.map((column) => (
            <TableHead key={column.key} className={column.format ? 'text-right' : ''}>
              {column.label}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {tableRows.map((row) => (
          <TableRow key={String(row.repo)}>
            {columns.map((column) => (
              <TableCell
                key={column.key}
                className={
                  column.format
                    ? 'text-right tabular-nums'
                    : column.key === 'repo'
                      ? 'font-medium'
                      : 'whitespace-normal'
                }
              >
                {column.format ? (
                  integer.format(Number(row[column.key]))
                ) : column.key === 'repo' ? (
                  <EntityLink kind="repo" name={String(row[column.key])} />
                ) : (
                  String(row[column.key])
                )}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );

  return (
    <ChartShell
      data={data}
      title={title}
      period={period}
      provenance={provenance}
      subtitle={[
        period !== title ? period : null,
        `${integer.format(data.nodes.length)} repositories · ${integer.format(data.edges.length)} links`,
      ]
        .filter(Boolean)
        .join(' · ')}
      toolbar={toolbar}
      controls={controls}
      empty={!data.nodes.length}
      focusFound={!dashboardFocus || dashboardFocus.dimension !== 'repo' || !!selected}
      printFilters={[
        { label: 'Date range', value: rangeText(data.window) },
        !!needle && { label: 'Search', value: `“${query.trim()}”` },
        minShared > (steps[0] ?? 0) && {
          label: 'Links shown',
          value: `${integer.format(edges.length)} of ${integer.format(data.edges.length)}`,
        },
        !matrix &&
          (view.zoom !== 1 || view.x !== 0 || view.y !== 0) && {
            label: 'Zoom',
            value: `${Math.round(view.zoom * 100)}%, as on screen`,
          },
      ]}
      printAspect={matrix ? 1.1 : bounds.width / bounds.height}
      windowNote={windowText(data.window)}
      csv={() => ({
        name: `${data.id}${focus ? `-${focus}` : ''}-selected`,
        title: `${title}${focus ? ` — ${focus} and its links` : ''}`,
        columns,
        rows: tableRows,
      })}
      chart={chart}
      table={table}
    />
  );
}
