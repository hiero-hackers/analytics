/**
 * Exercises every `ColumnFormat` value through the real `useDataTable` ->
 * `DataTable` -> `FormattedCell` pipeline, using a fixture with one column
 * per format. This is what keeps the TS union honest: if `ColumnFormat` ever
 * grows a value `FormattedCell` doesn't handle, or vice versa, this is where
 * that gap would show up as a wrong rendered cell rather than shipping quiet.
 */

import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DataTable } from '../components/DataTable';
import { FormattedCell } from '../components/FormattedCell';
import { useDataTable } from '../useDataTable';
import { ALL_FORMATS_DOC } from './fixtures';

/** Renders the fixture through the real column-format pipeline for assertions below. */
function Harness() {
  const table = useDataTable(ALL_FORMATS_DOC.columns, ALL_FORMATS_DOC.rows, 'all-formats');
  return <DataTable table={table} />;
}

describe('FormattedCell', () => {
  it('renders every supported format correctly', () => {
    render(<Harness />);
    const row = screen.getAllByRole('row')[1]; // [0] is the header row

    expect(within(row).getByText('HIP-1200')).toBeInTheDocument();
    expect(within(row).getByText('2026-07-20')).toBeInTheDocument();
    expect(within(row).getByRole('link', { name: 'open ↗' })).toHaveAttribute(
      'href',
      'https://example.test/pr/1',
    );
    expect(within(row).getByText('merged')).toBeInTheDocument();
    expect(within(row).getByText('Final')).toBeInTheDocument();
    expect(within(row).getByText('✓')).toBeInTheDocument();
    expect(within(row).getByText('present')).toBeInTheDocument();
    expect(within(row).getByText('2,490')).toBeInTheDocument();
    expect(within(row).getByText('62%')).toBeInTheDocument();
    expect(within(row).getByText('overdue')).toBeInTheDocument();
  });

  it('renders every staleness bucket with a distinct label', () => {
    const buckets: [string, string][] = [
      ['never_released', 'never released'],
      ['overdue', 'overdue'],
      ['watch', 'watch'],
      ['on_pace', 'on pace'],
      ['insufficient_history', 'not enough history'],
    ];

    for (const [value, label] of buckets) {
      const doc = {
        ...ALL_FORMATS_DOC,
        rows: [{ ...ALL_FORMATS_DOC.rows[0], staleness: value }],
      };

      function OneRow() {
        const table = useDataTable(doc.columns, doc.rows, 'one-row');
        return <DataTable table={table} />;
      }

      const { unmount } = render(<OneRow />);
      expect(screen.getByText(label)).toBeInTheDocument();
      unmount();
    }
  });
});

describe('Modern table cells', () => {
  it('draws a share as its figure plus a bar on a fixed 0–100 track', () => {
    const { container } = render(<FormattedCell value={95} format="percent" />);
    expect(container).toHaveTextContent('95%');
    const bar = container.querySelector('[aria-hidden="true"] > span') as HTMLElement;
    expect(bar.style.width).toBe('95%');
    // Out-of-range values never overflow the track.
    const { container: over } = render(<FormattedCell value={140} format="percent" />);
    expect((over.querySelector('[aria-hidden="true"] > span') as HTMLElement).style.width).toBe(
      '100%',
    );
  });

  it('says "none" for an empty cell instead of leaving it blank', () => {
    render(<FormattedCell value={null} format="date" />);
    expect(screen.getByLabelText('none')).toHaveTextContent('—');
  });

  it('links a repository, resolving a bare name against the shown organisation', async () => {
    const { RepoCell } = await import('../components/RepoCell');
    const { OrgContext } = await import('../orgContext');
    render(
      <OrgContext.Provider value="hiero-ledger">
        <RepoCell name="hiero-sdk-go" />
        <RepoCell name="hiero-hackers/analytics" />
        <RepoCell name="not a repo" />
      </OrgContext.Provider>,
    );
    expect(screen.getByRole('link', { name: 'hiero-sdk-go' })).toHaveAttribute(
      'href',
      'https://github.com/hiero-ledger/hiero-sdk-go',
    );
    expect(screen.getByRole('link', { name: 'hiero-hackers/analytics' })).toHaveAttribute(
      'href',
      'https://github.com/hiero-hackers/analytics',
    );
    expect(screen.getByText('not a repo').closest('a')).toBeNull();
  });

  it('gives a governance role its chart colour and keeps the word', async () => {
    const { RoleCell } = await import('../components/RoleCell');
    const { container } = render(<RoleCell role="committer" />);
    expect(container).toHaveTextContent('committer');
    expect(
      (container.querySelector('[aria-hidden="true"]') as HTMLElement).style.backgroundColor,
    ).toBe('var(--chart-committer)');
  });
});
