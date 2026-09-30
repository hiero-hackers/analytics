/**
 * The `matrix` kind: a heatmap as an ARIA grid with every cell labelled. One cell
 * is in the tab order, arrow keys move between cells, and the focused or hovered
 * cell is read out above the grid.
 */

import { useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { useElementSize } from '@/hooks/use-element-size';
import { CrosshairIcon } from 'lucide-react';
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
import type { ColumnSpec, MatrixDocument, Row } from '../../api';
import { dimensionOf, matches as focusMatches, toggle, useFocus } from '../../focus';
import { useUrlFlag, useUrlParam } from '../../urlState';
import { ContributorCell } from '../ContributorCell';
import { EntityLink } from '../EntityLink';
import { entityKindOf } from '../../entities';
import { ChartShell, TABLE_CONTAINER, type SheetBox, type ViewProps } from './ChartShell';
import { decimal, formatBucket, integer, plural, rangeText, shade, windowText } from './format';

const MONTH = /^\d{4}-\d{2}$/;
/** Printed rows shrink to fit the page between these heights, then run onto another page. */
const PRINT_ROW = { min: 16, max: 30, avatar: 22 };
/** Rough width of a 10px printed character, for sizing the printed name column. */
const PRINT_CHAR = 6;
/** The printed grid's column headings and colour scale, until measured. */
const PRINT_FRAME = { head: 48, legend: 24 };
/** Between printed rows (border-spacing), and around the grid (its border, the legend's gap). */
const PRINT_ROW_GAP = 2;
const PRINT_CHROME = 16;

function cellStyle(level: number | null, steps: number) {
  if (level === null || level === 0) return undefined;
  // Map any step count onto the five theme shades.
  const heat = Math.max(1, Math.round((level / steps) * 5));
  return {
    backgroundColor: `var(--heat-${heat})`,
    color: heat >= 3 ? 'var(--on-heat-high)' : 'var(--on-heat-low)',
  };
}

export function MatrixView({ data, title, period, provenance }: ViewProps<MatrixDocument>) {
  const [query, setQuery] = useUrlParam(`${data.id}.q`);
  const [showAll, setShowAll] = useUrlFlag(`${data.id}.all`);
  const [focus, setFocus] = useFocus();
  const dimension = dimensionOf(data.row.key);
  const [active, setActive] = useState<[number, number]>([0, 0]);
  const [readout, setReadout] = useState<[number, number] | null>(null);
  const gridRef = useRef<HTMLTableElement>(null);
  // Measured on the printed sheet only, where the rows share out the height they leave.
  const [headRef, head] = useElementSize();
  const [legendRef, legendBox] = useElementSize();
  const format = (value: unknown) =>
    (data.value_format === 'integer' ? integer : decimal).format(Number(value));
  const columnLabel = (label: string) => (MONTH.test(label) ? formatBucket(label, 'month') : label);
  const nouns = plural(data.row.label);

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return data.rows;
    return data.rows.filter((row) =>
      [row[data.row.key], data.sublabel ? row[data.sublabel.key] : '']
        .join(' ')
        .toLowerCase()
        .includes(needle),
    );
  }, [data, query]);
  // A search always shows every match; otherwise the top rows come first.
  const limited = !query && data.top_n !== null && matches.length > data.top_n;
  const focusRow = matches.find((row) => focusMatches(focus, dimension, row[data.row.key]));
  const top = limited && !showAll ? matches.slice(0, data.top_n ?? undefined) : matches;
  // The focused row leads the grid, wherever it ranks, so the focus is always in view.
  const shown = focusRow ? [focusRow, ...top.filter((row) => row !== focusRow)] : top;
  const [activeRow, activeColumn] = [
    Math.min(active[0], Math.max(shown.length - 1, 0)),
    Math.min(active[1], data.columns.length - 1),
  ];

  const describe = (row: Row, column: MatrixDocument['columns'][number]) => {
    const value = row[column.key];
    const text = value === null ? (data.missing ?? 'No value') : format(value);
    return `${String(row[data.row.key])}, ${columnLabel(column.label)}: ${text}`;
  };

  const move = (event: KeyboardEvent, r: number, c: number) => {
    const last = [shown.length - 1, data.columns.length - 1];
    const next: Record<string, [number, number]> = {
      ArrowUp: [Math.max(0, r - 1), c],
      ArrowDown: [Math.min(last[0], r + 1), c],
      ArrowLeft: [r, Math.max(0, c - 1)],
      ArrowRight: [r, Math.min(last[1], c + 1)],
      Home: [r, 0],
      End: [r, last[1]],
    };
    const target = next[event.key];
    if (!target) return;
    event.preventDefault();
    setActive(target);
    setReadout(target);
    gridRef.current?.querySelector<HTMLElement>(`[data-cell="${target[0]}:${target[1]}"]`)?.focus();
  };

  const columns: ColumnSpec[] = [
    { key: data.row.key, label: data.row.label },
    ...(data.sublabel ? [data.sublabel] : []),
    ...data.columns.map((column) => ({
      key: column.key,
      label: column.label,
      format: 'number' as const,
    })),
    ...(data.total ? [{ ...data.total, format: 'number' as const }] : []),
  ];
  const step = (data.scale.max - data.scale.min) / data.scale.steps;
  const legend = Array.from({ length: data.scale.steps }, (_, i) => {
    const low = data.scale.min + step * i;
    const high = data.scale.min + step * (i + 1);
    // Upper bounds are inclusive: a value on a boundary takes the lower shade.
    return { level: i + 1, text: `${format(low)}–${format(high)}` };
  });
  const focused = readout ? shown[readout[0]] : undefined;

  const controls = (
    <Input
      className="h-8 max-w-xs"
      placeholder={`Search ${nouns}…`}
      aria-label={`Search ${nouns}`}
      value={query}
      onChange={(event) => {
        setQuery(event.target.value);
        setActive([0, 0]);
        setReadout(null);
      }}
    />
  );

  // Paper fits every column to the page width, and the rows to its height where they can.
  const chart = (_expanded: boolean, sheet?: SheetBox) => {
    const rowHeight = sheet
      ? Math.min(
          PRINT_ROW.max,
          Math.max(
            data.avatars ? PRINT_ROW.avatar : PRINT_ROW.min,
            Math.floor(
              (sheet.height -
                (head?.height ?? PRINT_FRAME.head) -
                (legendBox?.height ?? PRINT_FRAME.legend) -
                PRINT_CHROME) /
                Math.max(shown.length, 1),
            ) - PRINT_ROW_GAP,
          ),
        )
      : undefined;
    // Wide enough that names print on one line, with the role beside them.
    const nameWidth = sheet
      ? Math.min(
          sheet.width * 0.28,
          24 +
            (data.avatars ? 26 : 0) +
            PRINT_CHAR *
              Math.max(
                data.row.label.length,
                ...shown.map(
                  (row) =>
                    String(row[data.row.key]).length +
                    (data.sublabel ? String(row[data.sublabel.key] ?? '').length + 3 : 0),
                ),
              ),
        )
      : undefined;
    return (
      <div className="space-y-3">
        {!sheet && (
          <p aria-live="polite" className="min-h-5 text-xs text-muted-foreground">
            {focused && readout
              ? `${describe(focused, data.columns[readout[1]])} (${data.value_label.toLowerCase()})`
              : 'Hover a cell, or focus the grid and use the arrow keys, to read exact values.'}
          </p>
        )}
        <div className={sheet ? 'rounded-lg border' : 'overflow-x-auto rounded-lg border'}>
          <table
            // The printed copy is not the grid a reader navigates.
            ref={sheet ? undefined : gridRef}
            role="grid"
            aria-label={`${title}: ${data.value_label} by ${data.row.label.toLowerCase()}`}
            aria-rowcount={shown.length + 1}
            className={
              sheet
                ? 'w-full table-fixed border-separate border-spacing-0.5 text-[10px] leading-tight'
                : 'w-full border-separate border-spacing-0.5 text-xs'
            }
          >
            <thead ref={sheet ? headRef : undefined}>
              <tr>
                <th
                  scope="col"
                  className="sticky left-0 bg-card px-2 py-1.5 text-left font-medium"
                  style={sheet ? { width: nameWidth } : undefined}
                >
                  {data.row.label}
                </th>
                {data.columns.map((column) => (
                  <th
                    key={column.key}
                    scope="col"
                    className={
                      sheet
                        ? 'px-0 py-1 text-center text-[9px] font-medium break-words hyphens-auto'
                        : 'max-w-24 px-1 py-1.5 text-center font-medium break-words'
                    }
                  >
                    {columnLabel(column.label)}
                  </th>
                ))}
                {data.total && (
                  <th
                    scope="col"
                    className="px-2 py-1.5 text-right font-medium"
                    style={sheet ? { width: 56 } : undefined}
                  >
                    {data.total.label}
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {shown.map((row, r) => (
                <tr
                  key={String(row[data.row.key])}
                  className={
                    row === focusRow ? 'outline-2 -outline-offset-1 outline-link' : undefined
                  }
                  style={rowHeight ? { height: rowHeight } : undefined}
                >
                  <th
                    scope="row"
                    className={`sticky left-0 bg-card px-2 text-left font-normal ${sheet ? 'py-0' : 'max-w-56 py-1'}`}
                  >
                    <span
                      className={sheet ? 'flex items-baseline gap-1' : 'flex items-center gap-1'}
                    >
                      {dimension && (
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          className={row === focusRow ? 'text-link' : 'text-soft'}
                          aria-pressed={row === focusRow}
                          aria-label={`Focus the dashboard on ${String(row[data.row.key])}`}
                          title="Focus the dashboard on this row"
                          onClick={() => setFocus(toggle(focus, dimension, row[data.row.key]))}
                        >
                          <CrosshairIcon />
                        </Button>
                      )}
                      {data.avatars ? (
                        <ContributorCell login={String(row[data.row.key])} compact={!!sheet} />
                      ) : (
                        <span className="font-medium">
                          <EntityLink
                            kind={entityKindOf(dimension)}
                            name={String(row[data.row.key])}
                          />
                        </span>
                      )}
                      {sheet && data.sublabel && row[data.sublabel.key] ? (
                        <span className="text-soft">· {String(row[data.sublabel.key])}</span>
                      ) : null}
                    </span>
                    {!sheet && data.sublabel && row[data.sublabel.key] ? (
                      <span className="mt-0.5 block text-[11px] text-soft">
                        {String(row[data.sublabel.key])}
                      </span>
                    ) : null}
                  </th>
                  {data.columns.map((column, c) => {
                    const value = row[column.key];
                    const level = shade(value, data.scale);
                    return (
                      <td
                        key={column.key}
                        role="gridcell"
                        data-cell={`${r}:${c}`}
                        tabIndex={r === activeRow && c === activeColumn ? 0 : -1}
                        aria-label={describe(row, column)}
                        title={describe(row, column)}
                        onKeyDown={(event) => move(event, r, c)}
                        onFocus={() => {
                          setActive([r, c]);
                          setReadout([r, c]);
                        }}
                        onMouseEnter={() => setReadout([r, c])}
                        style={cellStyle(level, data.scale.steps)}
                        className={`${sheet ? 'px-0 py-0' : 'min-w-14 px-1.5 py-1.5'} rounded-sm text-center tabular-nums outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                          level === null
                            ? 'border border-dashed text-soft'
                            : level === 0
                              ? 'bg-muted/40 text-soft'
                              : ''
                        }`}
                      >
                        {value === null ? '?' : format(value)}
                      </td>
                    );
                  })}
                  {data.total && (
                    <td className="px-2 text-right font-semibold tabular-nums">
                      {format(row[data.total.key])}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div
          ref={sheet ? legendRef : undefined}
          className="flex flex-wrap items-center justify-between gap-2"
        >
          <div
            className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground"
            aria-label="Colour scale"
          >
            <span>{data.value_label}:</span>
            <span className="inline-flex items-center gap-1">
              <i className="inline-block size-3 rounded-sm bg-muted/40" /> {format(data.scale.min)}
            </span>
            {legend.map(({ level, text }) => (
              <span key={level} className="inline-flex items-center gap-1">
                <i
                  className="inline-block size-3 rounded-sm"
                  style={cellStyle(level, data.scale.steps)}
                />
                {text}
              </span>
            ))}
            {data.missing && <span>? {data.missing}</span>}
          </div>
          {limited && !sheet && (
            <Button variant="outline" size="sm" onClick={() => setShowAll(!showAll)}>
              {showAll
                ? `Show top ${data.top_n}`
                : `Show all ${integer.format(matches.length)} ${nouns}`}
            </Button>
          )}
        </div>
      </div>
    );
  };

  const table = (
    <Table containerClassName={TABLE_CONTAINER}>
      <TableHeader className="sticky top-0 bg-muted">
        <TableRow>
          {columns.map((column, i) => (
            <TableHead key={column.key} className={i ? 'text-right' : ''}>
              {column.label}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {matches.map((row) => (
          <TableRow key={String(row[data.row.key])}>
            {columns.map((column, i) => (
              <TableCell key={column.key} className={i ? 'text-right tabular-nums' : 'font-medium'}>
                {column.format === 'number'
                  ? row[column.key] === null
                    ? (data.missing ?? '—')
                    : format(row[column.key])
                  : String(row[column.key] ?? '')}
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
        `${integer.format(data.rows.length)} ${nouns} × ${data.columns.length} columns`,
      ]
        .filter(Boolean)
        .join(' · ')}
      controls={controls}
      empty={!matches.length}
      emptyText={query ? `No ${nouns} match “${query}”.` : undefined}
      focusFound={!focus || focus.dimension !== dimension || !!focusRow}
      printFilters={[
        { label: 'Date range', value: rangeText(data.window) },
        !!query && {
          label: 'Search',
          value: `“${query}” · ${integer.format(matches.length)} ${nouns}`,
        },
        limited && {
          label: 'Showing',
          value: showAll
            ? `all ${integer.format(matches.length)} ${nouns}`
            : `top ${data.top_n} of ${integer.format(matches.length)} ${nouns}`,
        },
      ]}
      // Wide when it has many columns, tall when it has many rows.
      printAspect={
        (200 + data.columns.length * 44 + (data.total ? 60 : 0)) / (40 + shown.length * 24)
      }
      windowNote={windowText(data.window)}
      csv={() => ({
        name: `${data.id}-selected`,
        title: `${title}${query ? ` — matching “${query}”` : ''}`,
        columns,
        // The data view and CSV carry every matching row, not only the charted top rows.
        rows: matches.map((row) =>
          Object.fromEntries(columns.map((column) => [column.key, row[column.key] ?? ''])),
        ),
      })}
      chart={chart}
      table={table}
    />
  );
}
