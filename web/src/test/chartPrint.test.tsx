import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import InteractiveChart from '../components/InteractiveChart';
import { exportName } from '../chartExport';
import { VariantTabs } from '../components/VariantTabs';
import { bucketLong, rangeText } from '../components/charts/format';
import {
  bestOrientation,
  contentBox,
  defaultPaper,
  filterLabel,
  PAPER_STORAGE_KEY,
  pageRule,
  pageTops,
  storedPaper,
} from '../chartPrint';
import { PrintSheetContext } from '../printContext';
import { PrintProvider } from '../printing';
import type { ChartVariant, MatrixDocument, TimeseriesDocument } from '../api';

const roles: TimeseriesDocument = {
  schema_version: 1,
  id: 'roles',
  org: 'test',
  kind: 'timeseries',
  source: 'roles.csv',
  metric: 'active_contributors_by_role',
  unit: 'Unique active contributors',
  population: 'Each person is counted once per bucket.',
  dimensions: ['period', 'series'],
  note: 'Read the bars left to right.',
  methodology: ['Resolve roles per bucket.'],
  generated_at: '2026-02-12T12:00:00Z',
  mark: 'bar',
  stacked: true,
  normalize: false,
  orientation: 'vertical',
  value_format: 'integer',
  rank: false,
  top_n: null,
  reference: null,
  details: [],
  series: [
    { key: 'general_user', label: 'General contributors', color: 'var(--chart-general)' },
    { key: 'triage', label: 'Triage', color: 'var(--chart-triage)' },
    { key: 'maintainer', label: 'Maintainers', color: 'var(--chart-maintainer)' },
  ],
  frequency: 'month',
  timezone: 'UTC',
  comparison: null,
  group: null,
  category: { key: 'bucket', label: 'Period (UTC)' },
  window: { kind: 'calendar', first: '2026-01', last: '2026-02' },
  rows: [
    { bucket: '2026-01', general_user: 10, triage: 2, maintainer: 5, partial: false },
    { bucket: '2026-02', general_user: 4, triage: 0, maintainer: 6, partial: true },
  ],
};

const heatmap: MatrixDocument = {
  schema_version: 1,
  id: 'heat',
  org: 'test',
  kind: 'matrix',
  source: 'activity.csv',
  metric: 'activity',
  unit: 'Weighted activity',
  population: 'Every repository with activity.',
  dimensions: ['repo', 'month'],
  row: { key: 'repo', label: 'Repository' },
  sublabel: null,
  total: null,
  columns: [
    { key: '2026-01', label: '2026-01' },
    { key: '2026-02', label: '2026-02' },
  ],
  value_label: 'Score',
  scale: { min: 0, max: 10, steps: 5 },
  missing: null,
  avatars: false,
  top_n: null,
  value_format: 'integer',
  window: { kind: 'trailing', days: 60, end: '2026-02-28T00:00:00Z' },
  rows: [
    { repo: 'hiero-sdk-js', '2026-01': 4, '2026-02': 8 },
    { repo: 'hiero-docs', '2026-01': 1, '2026-02': 0 },
  ],
};

const provenance = { git_sha: 'abc1234', data_as_of: '2026-02-12T12:00:00Z' };
const variant = (path: string): ChartVariant => ({
  label: '1 year',
  interactive: { kind: 'timeseries', path },
});
const serve = (document: unknown) =>
  vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => document } as Response);
const sheet = () => document.querySelector<HTMLElement>('[data-print-sheet]')!;
const printedFilters = () =>
  [...sheet().querySelectorAll('[data-print-filter]')].map((filter) =>
    filter.textContent?.replace(/\s+/g, ' '),
  );

beforeEach(() => {
  // Every element reports a laid-out size, so charts draw and the sheet measures itself.
  vi.stubGlobal(
    'ResizeObserver',
    class {
      report: ResizeObserverCallback;
      constructor(report: ResizeObserverCallback) {
        this.report = report;
      }
      observe(target: Element) {
        const size = { inlineSize: 900, blockSize: 120 };
        const entry = {
          target,
          contentRect: { width: 900, height: 340 },
          borderBoxSize: [size],
        };
        this.report([entry as unknown as ResizeObserverEntry], this as never);
      }
      unobserve() {}
      disconnect() {}
    },
  );
  vi.stubGlobal('fetch', vi.fn());
  window.print = vi.fn();
  window.localStorage.clear();
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('paper', () => {
  it('prints wide charts landscape and tall or square ones portrait', () => {
    expect(bestOrientation(2, 'a4')).toBe('landscape');
    expect(bestOrientation(1, 'a4')).toBe('portrait');
    expect(bestOrientation(0.5, 'letter')).toBe('portrait');
    expect(bestOrientation(3, 'letter')).toBe('landscape');
  });

  it('keeps the printable area inside the margins of the chosen paper', () => {
    const portrait = contentBox('a4', 'portrait');
    const landscape = contentBox('a4', 'landscape');
    expect(portrait.width).toBe(186);
    expect(landscape.width).toBe(273);
    // A millimetre in hand, so rounding never spills onto a blank second page.
    expect(portrait.height).toBeLessThan(297 - 24);
    expect(contentBox('letter', 'portrait').width).toBeCloseTo(191.9);
  });

  it('writes the page rule the browser prints with', () => {
    expect(pageRule('a4', 'landscape')).toContain('size: A4 landscape');
    expect(pageRule('letter', 'portrait')).toContain('size: letter portrait');
    // No page margin: the browser gets no room for its own date, title and URL.
    expect(pageRule('a4', 'portrait')).toContain('margin: 0;');
    expect(pageRule('a4', 'portrait')).toContain('@bottom-left { content: none; }');
  });

  it('defaults to the reader’s regional paper and remembers their choice', () => {
    expect(defaultPaper('en-US')).toBe('letter');
    expect(defaultPaper('en-CA')).toBe('letter');
    expect(defaultPaper('de-DE')).toBe('a4');
    expect(defaultPaper('en-GB')).toBe('a4');
    expect(defaultPaper('not a locale')).toBe('a4');
    window.localStorage.setItem(PAPER_STORAGE_KEY, 'a4');
    expect(storedPaper()).toBe('a4');
  });

  it('breaks pages between rows, leaving space rather than splitting one', () => {
    // Rows end at 100, 190, 290 and 390px; 200px fit on a page.
    expect(pageTops([100, 190, 290, 390], 400, 200)).toEqual([0, 190, 390]);
    // A sheet that fits needs no break.
    expect(pageTops([100], 180, 200)).toEqual([0]);
    // With no break in the lower half of a page, the page is cut where it ends.
    expect(pageTops([20], 450, 200)).toEqual([0, 200, 400]);
  });

  it('names downloaded files after the chart and its paper', () => {
    expect(exportName('Role activity', 'a4', 'landscape', 'pdf')).toBe(
      'role-activity-a4-landscape.pdf',
    );
    expect(exportName('Org scorecard — 2026', 'letter', 'portrait', 'png')).toBe(
      'org-scorecard-2026-letter-portrait.png',
    );
    expect(exportName('★', 'a4', 'portrait', 'jpg')).toBe('chart-a4-portrait.jpg');
  });

  it('names printed filters without repeating the chart title', () => {
    expect(filterLabel('Role activity chart style', 'Role activity')).toBe('Chart style');
    expect(filterLabel('Network: minimum shared members', 'Network')).toBe(
      'Minimum shared members',
    );
    expect(filterLabel('Time range', 'Role activity')).toBe('Time range');
  });

  it('states the dates a chart covers', () => {
    expect(bucketLong('2026-03', 'month')).toBe('Mar 2026');
    expect(bucketLong('2026-03-05', 'day')).toBe('Mar 5, 2026');
    expect(bucketLong('2026', 'year')).toBe('2026');
    expect(rangeText({ kind: 'trailing', days: 30, end: '2026-02-28T00:00:00Z' })).toBe(
      '2026-01-29 – 2026-02-28 (30 days)',
    );
    expect(rangeText({ kind: 'snapshot', days: null, end: '2026-02-28T00:00:00Z' })).toBe(
      'Snapshot on 2026-02-28',
    );
    expect(rangeText({ kind: 'all', days: null, end: '2026-02-28T00:00:00Z' })).toBe(
      'All recorded activity to 2026-02-28',
    );
  });

  it('turns a switch into a stated filter on the printed sheet', () => {
    render(
      <PrintSheetContext.Provider value={{ title: 'Role activity' }}>
        <VariantTabs
          appearance="segmented"
          labels={['Bars', 'Line']}
          active={1}
          onSelect={() => {}}
          ariaLabel="Role activity chart style"
        />
      </PrintSheetContext.Provider>,
    );
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument();
    expect(screen.getByText('Chart style')).toBeInTheDocument();
    expect(screen.getByText('Line')).toBeInTheDocument();
  });
});

describe('Print chart', () => {
  it('previews the chart with its title, selection, date range and legend', async () => {
    serve({ ...roles, id: 'preview' });
    render(
      <InteractiveChart
        variant={variant('test/preview.json')}
        title="Role activity"
        provenance={provenance}
      />,
    );
    await userEvent.click(await screen.findByRole('radio', { name: 'Line' }));
    await userEvent.click(screen.getByRole('button', { name: 'Triage' }));
    await userEvent.click(screen.getByRole('button', { name: 'Print chart: Role activity' }));

    const dialog = await screen.findByRole('dialog', { name: 'Print preview' });
    expect(within(sheet()).getByRole('heading', { name: 'Role activity' })).toBeInTheDocument();
    expect(printedFilters()).toEqual([
      'View 1 year',
      'Chart style Line',
      'Line stacking Cumulative',
      'Scale Counts',
      'Date range Jan 2026 – Feb 2026 · 2 buckets',
      'Hidden series Triage',
    ]);
    // The legend names what is drawn; the hidden series is listed among the filters.
    const legend = within(sheet()).getByRole('group', { name: 'Visible series' });
    expect(within(legend).getByRole('button', { name: 'Triage' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
    expect(sheet()).toHaveTextContent(roles.population);
    // No source line, link or date to crowd the chart; the date is added on request.
    expect(sheet()).not.toHaveTextContent('abc1234');
    expect(sheet()).not.toHaveTextContent('Source generated');
    expect(sheet()).not.toHaveTextContent(window.location.href);
    expect(sheet()).not.toHaveTextContent(/Printed \d{4}/);
    await userEvent.click(
      within(within(dialog).getByRole('radiogroup', { name: 'Printed date' })).getByRole('radio', {
        name: 'Include',
      }),
    );
    expect(sheet()).toHaveTextContent(/Printed \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC/);
    // The printed copy offers no controls of its own.
    expect(within(sheet()).queryByRole('radiogroup')).not.toBeInTheDocument();
    expect(within(dialog).getByText(/on Letter landscape paper, one page/)).toBeInTheDocument();
  });

  it('prints the sheet alone on the chosen paper and restores the page afterwards', async () => {
    serve({ ...roles, id: 'paper' });
    render(
      <InteractiveChart
        variant={variant('test/paper.json')}
        title="Role activity"
        provenance={provenance}
      />,
    );
    await userEvent.click(
      await screen.findByRole('button', { name: 'Print chart: Role activity' }),
    );
    const dialog = await screen.findByRole('dialog', { name: 'Print preview' });
    expect(document.documentElement.dataset.printScope).toBe('chart');
    const pageStyle = () => dialog.querySelector('style')?.textContent;
    expect(pageStyle()).toContain('size: letter landscape');

    await userEvent.click(within(dialog).getByRole('radio', { name: 'A4' }));
    await userEvent.click(within(dialog).getByRole('radio', { name: 'Portrait' }));
    expect(pageStyle()).toContain('size: A4 portrait');
    expect(window.localStorage.getItem(PAPER_STORAGE_KEY)).toBe('a4');
    expect(within(dialog).getByText(/on A4 portrait paper/)).toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole('button', { name: 'Print' }));
    await waitFor(() => expect(window.print).toHaveBeenCalledTimes(1));

    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Print preview' })).not.toBeInTheDocument(),
    );
    expect(document.documentElement.dataset.printScope).toBeUndefined();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Print chart: Role activity' })).toHaveFocus(),
    );
  });

  it('adds the reading notes and methodology only on request', async () => {
    serve({ ...roles, id: 'notes' });
    render(
      <InteractiveChart
        variant={variant('test/notes.json')}
        title="Role activity"
        provenance={provenance}
      />,
    );
    await userEvent.click(
      await screen.findByRole('button', { name: 'Print chart: Role activity' }),
    );
    const dialog = await screen.findByRole('dialog', { name: 'Print preview' });
    expect(sheet()).not.toHaveTextContent('Resolve roles per bucket.');
    await userEvent.click(
      within(
        within(dialog).getByRole('radiogroup', { name: 'How to read it and methodology' }),
      ).getByRole('radio', { name: 'Include' }),
    );
    expect(sheet()).toHaveTextContent('Read the bars left to right.');
    expect(sheet()).toHaveTextContent('Resolve roles per bucket.');
  });

  it('explains that there is nothing to print instead of opening an empty preview', async () => {
    serve(heatmap);
    render(
      <InteractiveChart
        variant={{ ...variant('test/heat.json'), interactive: { kind: 'matrix', path: 'x' } }}
        title="Activity"
        provenance={provenance}
      />,
    );
    await userEvent.type(
      await screen.findByRole('textbox', { name: 'Search repositories' }),
      'nothing-matches',
    );
    const print = screen.getByRole('button', { name: 'Print chart: Activity' });
    await userEvent.click(print);
    const notice = screen.getByRole('alert');
    expect(notice).toHaveTextContent('Nothing to print for this selection');
    expect(notice).toHaveTextContent('No repositories match “nothing-matches”.');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(window.print).not.toHaveBeenCalled();

    // The message stands for that selection only.
    await userEvent.clear(screen.getByRole('textbox', { name: 'Search repositories' }));
    expect(screen.queryByText('Nothing to print for this selection')).not.toBeInTheDocument();
    await userEvent.type(screen.getByRole('textbox', { name: 'Search repositories' }), 'docs');
    await userEvent.click(print);
    await screen.findByRole('dialog', { name: 'Print preview' });
    expect(printedFilters()).toContain('Search “docs” · 1 repositories');
    expect(printedFilters()).toContain('Date range 2025-12-30 – 2026-02-28 (60 days)');
  });

  it('leaves the tab’s own print mode alone while a chart prints', () => {
    render(
      <PrintProvider>
        <p>tab</p>
      </PrintProvider>,
    );
    document.documentElement.dataset.printScope = 'chart';
    try {
      window.dispatchEvent(new Event('beforeprint'));
      expect(document.documentElement.dataset.printing).toBeUndefined();
    } finally {
      delete document.documentElement.dataset.printScope;
    }
    window.dispatchEvent(new Event('beforeprint'));
    expect(document.documentElement.dataset.printing).toBe('true');
    window.dispatchEvent(new Event('afterprint'));
    expect(document.documentElement.dataset.printing).toBeUndefined();
  });
});
