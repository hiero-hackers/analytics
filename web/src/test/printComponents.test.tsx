import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ChartSection } from '../api';
import { ChartSectionCard } from '../components/ChartSectionCard';
import { CoverageMatrix } from '../components/CoverageMatrix';
import { MetricTiles } from '../components/MetricTiles';
import { PeriodTabs } from '../components/PeriodTabs';
import { StatusBoard } from '../components/StatusBoard';
import { VariantTabs } from '../components/VariantTabs';
import { BOARD_DOC, MANIFEST, MATRIX_DOC } from './fixtures';

const printState = vi.hoisted(() => ({ printing: false }));
vi.mock('../printContext', () => ({
  usePrintMode: () => printState.printing,
  PRINT_ROW_LIMIT: 500,
}));

beforeEach(() => {
  printState.printing = false;
});

const slideshow: ChartSection = {
  id: 'activity',
  macro: 'Governance',
  title: 'Activity',
  description: 'Selected contributor activity.',
  slideshow: true,
  charts: [
    {
      title: 'Contributors',
      variants: [
        { label: 'All', file: 'all.png' },
        { label: 'Active', file: 'active.png' },
      ],
    },
    {
      title: 'Pipeline',
      variants: [
        { label: 'By year', file: 'year.png' },
        { label: 'By month', file: 'month.png' },
      ],
    },
  ],
};

describe('Chart printing', () => {
  it('prints every slide with its selected variant and restores the screen state', async () => {
    const card = <ChartSectionCard section={slideshow} provenance={MANIFEST.provenance} />;
    const { rerender } = render(card);
    await userEvent.click(screen.getByRole('button', { name: 'Active' }));
    await userEvent.click(screen.getByRole('button', { name: 'Next ›' }));
    await userEvent.click(screen.getByRole('button', { name: 'By month' }));

    expect(screen.queryByRole('img', { name: 'Contributors' })).not.toBeInTheDocument();
    // Hidden slides still fetch their active source before a native print.
    expect(screen.getByAltText('Contributors')).toHaveAttribute('loading', 'eager');

    printState.printing = true;
    rerender(<ChartSectionCard section={slideshow} provenance={MANIFEST.provenance} />);

    expect(screen.getByRole('img', { name: 'Contributors' })).toHaveAttribute(
      'src',
      expect.stringContaining('active.png'),
    );
    expect(screen.getByRole('img', { name: 'Pipeline' })).toHaveAttribute(
      'src',
      expect.stringContaining('month.png'),
    );
    expect(screen.getByText('Contributors — Active')).toBeInTheDocument();
    expect(screen.getByText('Pipeline — By month')).toBeInTheDocument();

    printState.printing = false;
    rerender(<ChartSectionCard section={slideshow} provenance={MANIFEST.provenance} />);
    expect(screen.queryByRole('img', { name: 'Contributors' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'By month' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await userEvent.click(screen.getByRole('button', { name: '‹ Prev' }));
    expect(screen.getByRole('button', { name: 'Active' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('names a failed chart and resets readiness when its variant changes', async () => {
    const section = { ...slideshow, charts: [slideshow.charts[0]] };
    const { rerender } = render(
      <ChartSectionCard section={section} provenance={MANIFEST.provenance} />,
    );
    fireEvent.error(screen.getByAltText('Contributors'));
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Could not load chart: Contributors (All).',
    );
    expect(screen.getByAltText('Contributors').closest('figure')).toHaveAttribute(
      'data-print-error',
    );

    await userEvent.click(screen.getByRole('button', { name: 'Active' }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByAltText('Contributors').closest('figure')).toHaveAttribute(
      'data-print-pending',
    );

    printState.printing = true;
    rerender(<ChartSectionCard section={section} provenance={MANIFEST.provenance} />);
    expect(screen.getByText(/Chart still loading: Contributors \(Active\)/)).toBeInTheDocument();
    fireEvent.load(screen.getByAltText('Contributors'));
    expect(screen.queryByText(/Chart still loading/)).not.toBeInTheDocument();
    expect(screen.getByAltText('Contributors').closest('figure')).not.toHaveAttribute(
      'data-print-pending',
    );
  });
});

describe('Structured dashboard content in print', () => {
  it('keeps matrix filters and prints every component count without interactive cells', async () => {
    const props = { view: MATRIX_DOC, evidence: new Map(), jump: null };
    const { rerender } = render(<CoverageMatrix {...props} />);
    await userEvent.type(
      screen.getByPlaceholderText('Filter by HIP number or title…'),
      'Throughput',
    );
    await userEvent.click(screen.getByRole('button', { name: 'Approved' }));
    const screenTable = screen.getByRole('table');

    printState.printing = true;
    rerender(<CoverageMatrix {...props} />);
    expect(screen.getByText(/Showing 1 of 3 rows. Governance: Approved./)).toHaveTextContent(
      'Filter: “Throughput”.',
    );
    const table = screen.getByRole('table');
    expect(screenTable).toBeInTheDocument();
    expect(screenTable).not.toBeVisible();
    expect(table).toHaveTextContent('consensus 3/1');
    expect(table).toHaveTextContent('java 0/2 · go 0/0');
    expect(within(table).queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByText('HIP-1100')).not.toBeInTheDocument();

    printState.printing = false;
    rerender(<CoverageMatrix {...props} />);
    expect(screen.getByRole('table')).toBe(screenTable);
    expect(screen.getByPlaceholderText('Filter by HIP number or title…')).toHaveValue('Throughput');
    expect(screen.getByText('1 rows')).toBeInTheDocument();
    expect(screen.queryByText('HIP-1100')).not.toBeInTheDocument();
  });

  it('prints every board item with its title and status, then restores the selected chip', async () => {
    const onJump = vi.fn();
    const { rerender } = render(<StatusBoard view={BOARD_DOC} onJump={onJump} />);
    await userEvent.click(screen.getByRole('button', { name: 'HIP-1200' }));

    printState.printing = true;
    rerender(<StatusBoard view={BOARD_DOC} onJump={onJump} />);
    expect(screen.getByText(/Throughput \(Approved\)/)).toHaveTextContent('HIP-1200');
    expect(screen.getByText(/Airdrops \(Final\)/)).toHaveTextContent('HIP-1100');
    expect(screen.getByText(/Dormant \(Deferred\)/)).toHaveTextContent('HIP-1000');
    expect(screen.queryByRole('button')).not.toBeInTheDocument();

    printState.printing = false;
    rerender(<StatusBoard view={BOARD_DOC} onJump={onJump} />);
    await userEvent.click(screen.getByRole('button', { name: 'Show in coverage matrix ↓' }));
    expect(onJump).toHaveBeenCalledWith(1200);
  });

  it('bounds a large matrix and explicitly names omitted rows and the complete CSV', () => {
    printState.printing = true;
    const view = {
      ...MATRIX_DOC,
      rows: Array.from({ length: 503 }, (_, index) => ({
        ...MATRIX_DOC.rows[0],
        key: index,
        label: `HIP-${index}`,
      })),
    };
    render(<CoverageMatrix view={view} evidence={new Map()} jump={null} />);

    expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(501);
    expect(screen.getByRole('rowheader', { name: /HIP-499/ })).toBeInTheDocument();
    expect(screen.queryByRole('rowheader', { name: /HIP-500/ })).not.toBeInTheDocument();
    expect(screen.getByText(/3 matching rows are not printed/)).toHaveTextContent(
      'Download CSV from this matrix on the dashboard for the complete data.',
    );
  });

  it('keeps explainable KPI values in print as ordinary content', () => {
    printState.printing = true;
    render(
      <MetricTiles tiles={[{ label: 'Maintainers', value: '103', note: 'Counted by role.' }]} />,
    );
    expect(screen.getByText('Maintainers', { selector: 'div.metric-tile > div' })).toBeVisible();
    expect(screen.getByText('103', { selector: 'div.metric-tile > div' })).toBeVisible();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('prints a human-readable period label and an accurate unsupported-period fallback', () => {
    printState.printing = true;
    const props = { periods: ['30d'], labels: { '30d': '1 month' }, onChange: vi.fn() };
    const { rerender } = render(<PeriodTabs {...props} active="30d" />);
    expect(screen.getByText('Time range: 1 month')).toBeInTheDocument();
    rerender(<PeriodTabs {...props} active="7d" />);
    expect(screen.getByText('Time range: All time')).toBeInTheDocument();
  });

  it('retains period, variant and KPI controls so focus can return to the same element', () => {
    const content = () => (
      <>
        <PeriodTabs
          periods={['30d']}
          active="30d"
          labels={{ '30d': '1 month' }}
          onChange={() => {}}
        />
        <VariantTabs
          labels={['All', 'Active']}
          active={1}
          ariaLabel="Population"
          onSelect={() => {}}
        />
        <MetricTiles tiles={[{ label: 'Maintainers', value: '103', note: 'Counted by role.' }]} />
      </>
    );
    const { rerender } = render(content());
    const names = ['1 month', 'Active', 'Maintainers 103'];
    const controls = names.map((name) => screen.getByRole('button', { name }));
    printState.printing = true;
    rerender(content());
    for (const control of controls) {
      expect(control).toBeInTheDocument();
      expect(control).not.toBeVisible();
    }
    printState.printing = false;
    rerender(content());
    names.forEach((name, index) =>
      expect(screen.getByRole('button', { name })).toBe(controls[index]),
    );
  });
});
