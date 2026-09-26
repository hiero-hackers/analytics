/**
 * The `network` kind: repositories linked by shared members, drawn as SVG
 * from the layout the PNG uses (plotting/network.py), with its sizing rules —
 * bubble area ~ sqrt(active members), link width ~ shared members.
 *
 * Search or select a repository to highlight it and its neighbours; the
 * neighbour list and the data view say exactly how many members each link
 * shares. Pan by dragging, zoom with the buttons (or Ctrl/⌘ + wheel, so the
 * page still scrolls normally).
 */

import { useMemo, useRef, useState, type PointerEvent, type WheelEvent } from 'react';
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
import { ChartShell, TABLE_CONTAINER, type ViewProps } from './ChartShell';
import { integer, windowText } from './format';

/** SVG units per layout unit: roughly the PNG's points per unit at 16 inches wide. */
const UNIT = 110;
const PAD = 48;
const MIN_ZOOM = 0.5;
const MAX_ZOOM = 4;

const short = (repo: string) => (repo.startsWith('hiero-') ? repo.slice('hiero-'.length) : repo);
/** The PNG's marker area (140 + 260·√active, in pt²) as a radius, enlarged for card width. */
const radius = (active: number) => 1.6 * Math.sqrt((140 + 260 * Math.sqrt(active)) / Math.PI);

export function NetworkView({ data, title, period, provenance }: ViewProps<NetworkDocument>) {
  const [query, setQuery] = useUrlParam(`${data.id}.q`);
  // The selected repository *is* the dashboard focus: selecting one here also
  // filters every repository table, and a focus set elsewhere selects it here.
  const [dashboardFocus, setFocus] = useFocus();
  const selected =
    data.nodes.find((node) => focusMatches(dashboardFocus, 'repo', node.id))?.id ?? null;
  const setSelected = (id: string | null) => setFocus(id ? { dimension: 'repo', value: id } : null);
  const [focused, setFocused] = useState<string | null>(null);
  const [view, setView] = useState({ zoom: 1, x: 0, y: 0 });
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
    for (const edge of data.edges) {
      map.get(edge.source)?.push({ id: edge.target, shared: edge.shared });
      map.get(edge.target)?.push({ id: edge.source, shared: edge.shared });
    }
    for (const list of map.values())
      list.sort((a, b) => b.shared - a.shared || a.id.localeCompare(b.id));
    return map;
  }, [data]);

  const bounds = useMemo(() => {
    const xs = data.nodes.map((node) => node.x);
    const ys = data.nodes.map((node) => node.y);
    const [minX, maxX, minY, maxY] = [
      Math.min(...xs),
      Math.max(...xs),
      Math.min(...ys),
      Math.max(...ys),
    ];
    return {
      minX,
      maxY,
      width: (maxX - minX) * UNIT + PAD * 2 + 120,
      height: (maxY - minY) * UNIT + PAD * 2 + 40,
    };
  }, [data.nodes]);
  const place = (node: { x: number; y: number }) => ({
    cx: (node.x - bounds.minX) * UNIT + PAD + 60,
    cy: (bounds.maxY - node.y) * UNIT + PAD + 20,
  });
  const positions = new Map(data.nodes.map((node) => [node.id, place(node)]));
  const maxShared = Math.max(1, ...data.edges.map((edge) => edge.shared));

  const needle = query.trim().toLowerCase();
  const matches = new Set(
    needle
      ? data.nodes.filter((node) => node.id.toLowerCase().includes(needle)).map((n) => n.id)
      : [],
  );
  const focus = selected ?? (matches.size === 1 ? [...matches][0] : null);
  const lit = focus ? new Set([focus, ...(neighbours.get(focus) ?? []).map((n) => n.id)]) : null;
  const dimmed = (id: string) => (lit ? !lit.has(id) : needle ? !matches.has(id) : false);
  const isolated = data.nodes.filter((node) => !neighbours.get(node.id)?.length);

  const zoomBy = (factor: number) =>
    setView((current) => ({
      ...current,
      zoom: Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, current.zoom * factor)),
    }));
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
  const onWheel = (event: WheelEvent<SVGSVGElement>) => {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    zoomBy(event.deltaY < 0 ? 1.15 : 1 / 1.15);
  };

  const inScope = (id: string) => (lit ? lit.has(id) : needle ? matches.has(id) : true);
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

  const controls = (
    <div className="flex flex-wrap items-center gap-2">
      <Input
        className="max-w-xs"
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

  const chart = (expanded: boolean) => {
    const focusNode = focus ? data.nodes.find((node) => node.id === focus) : undefined;
    return (
      <div className="space-y-3">
        <div className="relative overflow-hidden rounded-lg border bg-card">
          <div className="absolute top-2 right-2 z-10 flex gap-1">
            <Button variant="outline" size="icon" aria-label="Zoom in" onClick={() => zoomBy(1.25)}>
              <PlusIcon />
            </Button>
            <Button variant="outline" size="icon" aria-label="Zoom out" onClick={() => zoomBy(0.8)}>
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
          <svg
            ref={svgRef}
            role="group"
            aria-label={`${title}: ${data.nodes.length} repositories, ${data.edges.length} links. Tab to a repository and press Enter to show its links.`}
            viewBox={`0 0 ${bounds.width} ${bounds.height}`}
            className={`block w-full cursor-grab touch-none select-none active:cursor-grabbing ${expanded ? 'max-h-[70vh]' : 'max-h-[560px]'}`}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={() => (drag.current = null)}
            onPointerLeave={() => (drag.current = null)}
            onWheel={onWheel}
            onKeyDown={(event) => event.key === 'Escape' && setSelected(null)}
          >
            <g
              transform={`translate(${cx} ${cy}) scale(${view.zoom}) translate(${view.x - cx} ${view.y - cy})`}
            >
              {data.edges.map((edge) => {
                const a = positions.get(edge.source)!;
                const b = positions.get(edge.target)!;
                const on = focus ? edge.source === focus || edge.target === focus : false;
                return (
                  <line
                    key={`${edge.source}|${edge.target}`}
                    x1={a.cx}
                    y1={a.cy}
                    x2={b.cx}
                    y2={b.cy}
                    stroke={on ? 'var(--ink)' : 'var(--edge-strong)'}
                    strokeOpacity={on ? 0.8 : focus ? 0.12 : 0.55}
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
                const ring = node.id === focus || node.id === focused || matches.has(node.id);
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
            · Bubble size = active {member} · link width = shared {member}
          </span>
        </div>
        {focusNode ? (
          <div className="rounded-lg border p-3 text-sm" aria-live="polite">
            <p className="font-semibold">
              {focusNode.id}{' '}
              <span className="font-normal text-muted-foreground">
                · {focusNode.category} · {integer.format(focusNode.active)} active of{' '}
                {integer.format(focusNode.total)} {member}
              </span>
            </p>
            {neighbours.get(focusNode.id)?.length ? (
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {neighbours.get(focusNode.id)!.map((link) => (
                  <li key={link.id}>
                    <Button variant="outline" size="sm" onClick={() => setSelected(link.id)}>
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
          <p className="text-xs text-muted-foreground">
            Select or search a repository to show its links. Drag to pan; zoom with the buttons or
            Ctrl/⌘ + scroll.
          </p>
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
                {column.format ? integer.format(Number(row[column.key])) : String(row[column.key])}
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
      controls={controls}
      empty={!data.nodes.length}
      focusFound={!dashboardFocus || dashboardFocus.dimension !== 'repo' || !!selected}
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
