/**
 * The arithmetic behind a series chart, kept out of the component so the numbers
 * it draws — visible totals, share normalisation, cumulative line stacks — can be
 * asserted directly. Sums run across the visible series of one row, never across
 * rows: a period or category is never re-aggregated.
 */

import type { Row, SeriesDocument } from '../../api';

type Series = SeriesDocument['series'][number];

/** A row as displayed: its category label, visible total, and (when normalised) shares. */
export type ViewRow = Row & { category: string; total: number; partial?: boolean };

/** The key a series' percentage of its row's visible total is stored under. */
export const share = (key: string) => `${key}__share`;
/** The running total up the stack to (and including) a series, drawn by cumulative lines. */
export const cumulative = (key: string) => `${key}__cumulative`;

const visibleTotal = (row: Row, visible: Series[]) =>
  visible.reduce((sum, series) => sum + Number(row[series.key]), 0);

export function viewRows(
  rows: Row[],
  {
    visible,
    categoryKey,
    group,
    normalized,
    stackedLines,
    rank,
  }: {
    visible: Series[];
    categoryKey: string;
    /** Keep only rows of this cohort (a categories document's group axis). */
    group?: { key: string; value: string | undefined } | null;
    /** Add each series' share of the row's visible total, in percent. */
    normalized: boolean;
    /** Add running totals up the stack, over shares when normalised. */
    stackedLines: boolean;
    /** Order by visible total, largest first; otherwise the source order stands. */
    rank: boolean;
  },
): ViewRow[] {
  const shown = rows
    .filter((row) => !group || row[group.key] === group.value)
    .map((row) => {
      const total = visibleTotal(row, visible);
      const shares = normalized
        ? Object.fromEntries(
            visible.map((series) => [
              share(series.key),
              total ? (Number(row[series.key]) / total) * 100 : 0,
            ]),
          )
        : {};
      let running = 0;
      const stacked = stackedLines
        ? Object.fromEntries(
            visible.map((series) => {
              running += Number(normalized ? shares[share(series.key)] : row[series.key]);
              return [cumulative(series.key), running];
            }),
          )
        : {};
      return { ...row, ...shares, ...stacked, category: String(row[categoryKey]), total };
    });
  if (rank) shown.sort((a, b) => b.total - a.total);
  return shown;
}

/** Every bucket's visible total, for the overview strip the span brush sits on. */
export const overviewTotals = (rows: Row[], visible: Series[]) =>
  rows.map((row) => ({ bucket: row.bucket, total: visibleTotal(row, visible) }));
