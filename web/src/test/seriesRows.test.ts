/**
 * The numbers a series chart draws: visible totals, shares, cumulative stacks and
 * ranking, asserted directly rather than through the rendered SVG.
 */

import { describe, expect, it } from 'vitest';
import { cumulative, overviewTotals, share, viewRows } from '../components/charts/seriesRows';

const series = [
  { key: 'a', label: 'A', color: 'red' },
  { key: 'b', label: 'B', color: 'blue' },
  { key: 'c', label: 'C', color: 'green' },
];
const rows = [
  { bucket: '2026-01', a: 1, b: 3, c: 0, partial: false },
  { bucket: '2026-02', a: 6, b: 2, c: 2, partial: true },
  { bucket: '2026-03', a: 0, b: 0, c: 0, partial: false },
];
const base = {
  visible: series,
  categoryKey: 'bucket',
  normalized: false,
  stackedLines: false,
  rank: false,
};

describe('viewRows', () => {
  it('totals only the visible series and keeps each row as it came', () => {
    const shown = viewRows(rows, { ...base, visible: series.slice(0, 2) });
    expect(shown.map((row) => [row.category, row.total])).toEqual([
      ['2026-01', 4],
      ['2026-02', 8],
      ['2026-03', 0],
    ]);
    // Hiding a series changes the total, never the row's own counts or partial flag.
    expect(shown[1]).toMatchObject({ a: 6, b: 2, c: 2, partial: true });
  });

  it('normalises each row to percentages of its visible total, zero for an empty row', () => {
    const shown = viewRows(rows, { ...base, normalized: true });
    expect([shown[0][share('a')], shown[0][share('b')], shown[0][share('c')]]).toEqual([25, 75, 0]);
    expect([shown[1][share('a')], shown[1][share('b')], shown[1][share('c')]]).toEqual([
      60, 20, 20,
    ]);
    expect([shown[2][share('a')], shown[2][share('b')]]).toEqual([0, 0]);
  });

  it('stacks cumulative lines up the series of one row, over counts or shares', () => {
    const counts = viewRows(rows, { ...base, stackedLines: true });
    expect(series.map((s) => counts[1][cumulative(s.key)])).toEqual([6, 8, 10]);
    // The top line is the visible total.
    expect(counts[1][cumulative('c')]).toBe(counts[1].total);

    const shares = viewRows(rows, { ...base, stackedLines: true, normalized: true });
    expect(series.map((s) => shares[0][cumulative(s.key)])).toEqual([25, 100, 100]);
  });

  it('never runs a cumulative total across rows', () => {
    const shown = viewRows(rows, { ...base, stackedLines: true });
    expect(shown[2][cumulative('c')]).toBe(0);
  });

  it('ranks by visible total when asked, and filters to one cohort', () => {
    const cohorts = [
      { stage: 'x', cohort: 'all', a: 1, b: 0, c: 0 },
      { stage: 'y', cohort: 'all', a: 5, b: 0, c: 0 },
      { stage: 'z', cohort: 'recent', a: 9, b: 0, c: 0 },
    ];
    const shown = viewRows(cohorts, {
      ...base,
      categoryKey: 'stage',
      group: { key: 'cohort', value: 'all' },
      rank: true,
    });
    expect(shown.map((row) => row.category)).toEqual(['y', 'x']);
    expect(viewRows(cohorts, { ...base, categoryKey: 'stage' }).map((row) => row.category)).toEqual(
      ['x', 'y', 'z'],
    );
  });
});

describe('overviewTotals', () => {
  it('gives every bucket the visible total, independent of any span', () => {
    expect(overviewTotals(rows, series.slice(1))).toEqual([
      { bucket: '2026-01', total: 3 },
      { bucket: '2026-02', total: 4 },
      { bucket: '2026-03', total: 0 },
    ]);
  });
});
