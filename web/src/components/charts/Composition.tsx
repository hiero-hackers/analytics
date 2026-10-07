/**
 * Single-series category forms: `Meter` leads with the headline status's share
 * of one track; `Funnel` sizes nested stages against the first and states each
 * step's conversion and drop-off. Every value is labelled, so nothing needs hover.
 */

import type { ChartSeries, Row } from '../../api';
import { integer, percent } from './format';

type Entry = Row & { category: string };

/** Headline first in the series hue; the remaining statuses in neutral steps. */
const NEUTRALS = ['var(--edge-strong)', 'var(--edge-input)', 'var(--raise)'];
const fill = (index: number, series: ChartSeries) =>
  index === 0 ? series.color : NEUTRALS[Math.min(index - 1, NEUTRALS.length - 1)];

const pct = (part: number, whole: number) => (whole ? (part / whole) * 100 : 0);

export function Meter({
  rows,
  series,
  unit,
  format,
}: {
  rows: Entry[];
  series: ChartSeries;
  unit: string;
  format: (value: number) => string;
}) {
  const value = (row: Entry) => Number(row[series.key]);
  const total = rows.reduce((sum, row) => sum + value(row), 0);
  const [head] = rows;
  const share = pct(value(head), total);
  const noun = unit.toLowerCase();
  const summary = rows
    .map(
      (row) => `${row.category} ${format(value(row))} (${percent.format(pct(value(row), total))}%)`,
    )
    .join(', ');
  return (
    <div className="space-y-4 py-2">
      <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-5xl leading-none font-semibold tracking-tight">
          {percent.format(share)}%
        </span>
        <span className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">{head.category}</span> ·{' '}
          {format(value(head))} of {format(total)} {noun}
        </span>
      </p>
      <div
        role="img"
        aria-label={`${format(total)} ${noun}: ${summary}.`}
        className="flex h-5 w-full gap-0.5 overflow-hidden rounded"
      >
        {rows.map((row, index) =>
          value(row) > 0 ? (
            <div
              key={row.category}
              title={`${row.category}: ${format(value(row))}`}
              className="h-full first:rounded-l last:rounded-r"
              style={{ flexGrow: value(row), flexBasis: 0, backgroundColor: fill(index, series) }}
            />
          ) : null,
        )}
      </div>
      <ul className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
        {rows.map((row, index) => (
          <li key={row.category} className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className="size-3 rounded-sm border border-edge-strong/60"
              style={{ backgroundColor: fill(index, series) }}
            />
            <span className="text-muted-foreground">{row.category}</span>
            <span className="font-semibold tabular-nums">{format(value(row))}</span>
            <span className="text-xs tabular-nums text-muted-foreground">
              {percent.format(pct(value(row), total))}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Funnel({
  rows,
  series,
  format,
}: {
  rows: Entry[];
  series: ChartSeries;
  format: (value: number) => string;
}) {
  const value = (row: Entry) => Number(row[series.key]);
  const first = value(rows[0]);
  return (
    <ol className="space-y-0 py-2" aria-label={`${rows.length} stages`}>
      {rows.map((row, index) => {
        const previous = index ? value(rows[index - 1]) : null;
        const width = Math.max(pct(value(row), first), value(row) > 0 ? 1.5 : 0);
        const lost = previous === null ? 0 : previous - value(row);
        return (
          <li key={row.category}>
            {previous !== null && (
              <p className="flex items-center justify-center gap-2 py-1 text-xs text-muted-foreground">
                <span aria-hidden="true">↓</span>
                <span>
                  <span className="font-medium text-foreground tabular-nums">
                    {percent.format(pct(value(row), previous))}%
                  </span>{' '}
                  continue
                </span>
                {lost > 0 && (
                  <span className="tabular-nums">· {integer.format(lost)} drop off</span>
                )}
              </p>
            )}
            <div className="grid grid-cols-[minmax(7rem,11rem)_1fr_auto] items-center gap-3">
              <span className="text-sm font-medium">{row.category}</span>
              <div className="flex h-9 justify-center rounded bg-raise/60">
                <div
                  className="h-full rounded"
                  style={{ width: `${width}%`, backgroundColor: series.color }}
                />
              </div>
              <span className="w-28 text-right text-sm">
                <span className="font-semibold tabular-nums">{format(value(row))}</span>{' '}
                <span className="text-xs tabular-nums text-muted-foreground">
                  {percent.format(pct(value(row), first))}% of first
                </span>
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
