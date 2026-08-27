/**
 * The virtualisation threshold: short tables must render whole, so the common
 * case keeps working without layout machinery.
 *
 * The virtualised path itself is deliberately not asserted here — it depends on
 * measured element heights, and jsdom performs no layout, so any assertion
 * would really be testing the stubs. It is verified in a real browser against
 * the deployed site (DOM node counts before/after), where the numbers mean
 * something.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { Row } from '../api';
import { DataTable, VIRTUALIZE_ABOVE } from '../components/DataTable';
import { useDataTable } from '../useDataTable';

function Harness({ rows }: { rows: Row[] }) {
  const table = useDataTable([{ key: 'n', label: 'n' }], rows, 'harness');
  return <DataTable table={table} />;
}

const makeRows = (count: number): Row[] =>
  Array.from({ length: count }, (_, index) => ({ n: index }));

describe('DataTable', () => {
  it('renders a table at the threshold whole', () => {
    render(<Harness rows={makeRows(VIRTUALIZE_ABOVE)} />);

    expect(screen.getAllByRole('row')).toHaveLength(VIRTUALIZE_ABOVE + 1); // + header
  });

  it('renders every row of a small table, in order', () => {
    render(<Harness rows={makeRows(5)} />);

    const cells = screen.getAllByRole('cell').map((cell) => cell.textContent);
    expect(cells).toEqual(['0', '1', '2', '3', '4']);
  });
});
