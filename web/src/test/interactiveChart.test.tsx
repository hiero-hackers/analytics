import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import InteractiveChart from '../components/InteractiveChart';
import { validateChartDocument } from '../chartData';
import { downloadCsv } from '../csv';
import type { CategoriesDocument, ChartDocument, ChartVariant, TimeseriesDocument } from '../api';

vi.mock('../csv', () => ({ downloadCsv: vi.fn() }));

const shared = {
  schema_version: 1 as const,
  org: 'test',
  source: 'roles.csv',
  metric: 'active_contributors_by_role',
  unit: 'Unique active contributors',
  population: 'Each person is counted once per bucket.',
  mark: 'bar' as const,
  stacked: true,
  normalize: false,
  orientation: 'vertical' as const,
  value_format: 'integer' as const,
  rank: false,
  top_n: null,
  reference: null,
  details: [],
  series: [
    { key: 'general_user', label: 'General contributors', color: 'var(--chart-general)' },
    { key: 'triage', label: 'Triage', color: 'var(--chart-triage)' },
    { key: 'committer', label: 'Committers', color: 'var(--chart-committer)' },
    { key: 'maintainer', label: 'Maintainers', color: 'var(--chart-maintainer)' },
  ],
  generated_at: '2026-02-12T12:00:00Z',
};
const data: TimeseriesDocument = {
  ...shared,
  id: 'roles',
  kind: 'timeseries',
  dimensions: ['period', 'series'],
  frequency: 'month',
  timezone: 'UTC',
  comparison: null,
  group: null,
  category: { key: 'bucket', label: 'Period (UTC)' },
  window: { kind: 'calendar', first: '2026-01', last: '2026-02' },
  rows: [
    { bucket: '2026-01', general_user: 10, triage: 2, committer: 3, maintainer: 5, partial: false },
    { bucket: '2026-02', general_user: 4, triage: 0, committer: 2, maintainer: 6, partial: true },
  ],
  note: 'Read the bars left to right.',
  stale: true,
};
const repos: CategoriesDocument = {
  ...shared,
  id: 'repos',
  kind: 'categories',
  dimensions: ['repo', 'series'],
  orientation: 'horizontal',
  rank: true,
  top_n: 10,
  group: null,
  category: { key: 'repo', label: 'Repository' },
  window: { kind: 'trailing', days: 30, end: '2026-02-12T12:00:00Z' },
  rows: Array.from({ length: 12 }, (_, i) => ({
    repo: `repo-${String(i).padStart(2, '0')}`,
    general_user: 12 - i,
    triage: 0,
    committer: 0,
    maintainer: i === 11 ? 50 : 0,
  })),
};
const funnel: CategoriesDocument = {
  ...shared,
  id: 'funnel',
  kind: 'categories',
  stacked: false,
  unit: 'HIP specs',
  dimensions: ['stage', 'cohort'],
  orientation: 'horizontal',
  category: { key: 'stage', label: 'Stage' },
  group: { key: 'cohort', label: 'Cohort', default: 'recent', values: ['all', 'recent'] },
  window: { kind: 'snapshot', days: null, end: '2026-02-12T12:00:00Z' },
  series: [{ key: 'hips', label: 'HIPs', color: 'var(--heat-4)' }],
  details: [{ key: 'pct', label: 'Share of proposed', format: 'percent' }],
  rows: [
    { cohort: 'all', stage: 'proposed', hips: 158, pct: 100 },
    { cohort: 'all', stage: 'approved', hips: 143, pct: 91 },
    { cohort: 'recent', stage: 'proposed', hips: 35, pct: 100 },
    { cohort: 'recent', stage: 'approved', hips: 31, pct: 88.6 },
  ],
};
const provenance = { git_sha: 'abc', data_as_of: null };
const variant = (path: string, kind: ChartDocument['kind'] = 'timeseries'): ChartVariant => ({
  label: '1 year',
  file: 'legacy.png',
  image_available: false,
  interactive: { kind, path },
});
const serve = (document: unknown) =>
  vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => document } as Response);
const firstCells = () =>
  screen
    .getAllByRole('row')
    .slice(1)
    .map((row) => within(row).getAllByRole('cell')[0].textContent);

beforeEach(() => {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => data }));
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

async function showData() {
  await screen.findByRole('radio', { name: 'Data' });
  await userEvent.click(screen.getByRole('radio', { name: 'Data' }));
}

describe('Interactive charts', () => {
  it('uses the selected series for the table and downloaded CSV', async () => {
    render(
      <InteractiveChart
        variant={variant('test/selection.json')}
        title="Role activity"
        provenance={provenance}
      />,
    );
    await showData();
    expect(within(screen.getByRole('table')).getByText('20')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Maintainers' }));
    expect(screen.getByRole('button', { name: 'Maintainers' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
    expect(screen.queryByRole('columnheader', { name: 'Maintainers' })).not.toBeInTheDocument();
    expect(within(screen.getByRole('table')).getByText('15')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Download CSV' }));
    const payload = vi.mocked(downloadCsv).mock.calls[0][0];
    expect(payload.columns.map((column) => column.key)).not.toContain('maintainer');
    expect(payload.rows[0]).toEqual({
      bucket: '2026-01',
      general_user: 10,
      triage: 2,
      committer: 3,
      total: 15,
      partial: false,
    });
    expect(payload.dataAsOf).toBe(data.generated_at);
    expect(screen.getByText(data.population)).toBeInTheDocument();
    expect(screen.getByText(data.note!)).toBeInTheDocument();
  });

  it('replaces the dataset when the period changes, without showing stale rows', async () => {
    const rendered = render(
      <InteractiveChart
        variant={variant('test/first.json')}
        title="Role activity"
        provenance={provenance}
      />,
    );
    await showData();
    let resolve!: (value: Response) => void;
    vi.mocked(fetch).mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        }) as Promise<Response>,
    );
    rendered.rerender(
      <InteractiveChart
        variant={{ ...variant('test/second.json'), label: 'Week' }}
        title="Role activity"
        provenance={provenance}
      />,
    );
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Loading');
    resolve({
      ok: true,
      json: async () => ({
        ...data,
        frequency: 'day',
        rows: [{ ...data.rows[0], bucket: '2026-02-12' }],
        window: { kind: 'calendar', first: '2026-02-12', last: '2026-02-12' },
      }),
    } as Response);
    await showData();
    expect(screen.getByText('2026-02-12', { selector: 'td' })).toBeInTheDocument();
    expect(screen.queryByText('2026-01', { selector: 'td' })).not.toBeInTheDocument();
  });

  it('retries failed requests and keeps a legacy fallback available', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error('offline'));
    render(
      <InteractiveChart
        variant={variant('test/retry.json')}
        title="Role activity"
        provenance={provenance}
        fallback={<img src="legacy.png" alt="Legacy chart" />}
      />,
    );
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be loaded');
    expect(screen.getByRole('img', { name: 'Legacy chart' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Retry chart' }));
    await screen.findByRole('button', { name: 'Maintainers' });
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('opens an interactive dialog and returns focus to its trigger', async () => {
    render(
      <InteractiveChart
        variant={variant('test/dialog.json')}
        title="Role activity"
        provenance={provenance}
      />,
    );
    const expand = await screen.findByRole('button', {
      name: 'Expand interactive chart: Role activity',
    });
    await userEvent.click(expand);
    const dialog = screen.getByRole('dialog');
    await userEvent.click(within(dialog).getByRole('radio', { name: 'Data' }));
    expect(within(dialog).getByRole('table')).toBeInTheDocument();
    fireEvent.keyDown(dialog, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Expand interactive chart: Role activity' }),
      ).toHaveFocus(),
    );
  });

  it('renders an empty state rather than a misleading zero chart', async () => {
    serve({ ...data, rows: [], window: { kind: 'calendar', first: null, last: null } });
    render(
      <InteractiveChart
        variant={variant('test/empty.json')}
        title="Role activity"
        provenance={provenance}
      />,
    );
    expect(await screen.findByText('No data is available for this selection.')).toBeInTheDocument();
  });

  it('ranks categories by the series on show and lists every row as data', async () => {
    serve(repos);
    render(
      <InteractiveChart
        variant={variant('test/repos.json', 'categories')}
        title="By repository"
        provenance={provenance}
      />,
    );
    expect(
      await screen.findByRole('button', { name: 'Show all 12 repositories' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Window: the 30 days before 2026-02-12 12:00 UTC.', { exact: false }),
    ).toBeInTheDocument();
    await showData();
    expect(firstCells()).toHaveLength(12);
    expect(firstCells()[0]).toBe('repo-11');
    expect(
      screen.queryByRole('columnheader', { name: 'Possibly incomplete' }),
    ).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Maintainers' }));
    expect(firstCells()[0]).toBe('repo-00');
  });

  it('keeps cohorts apart and shows details beside the counts', async () => {
    serve(funnel);
    render(
      <InteractiveChart
        variant={variant('test/funnel.json', 'categories')}
        title="Funnel"
        provenance={provenance}
      />,
    );
    await showData();
    // A single series has nothing to toggle and no total to add up.
    expect(screen.queryByRole('group', { name: 'Visible series' })).not.toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'recent' })).toHaveAttribute('data-state', 'on');
    expect(within(screen.getByRole('table')).getByText('88.6%')).toBeInTheDocument();
    expect(within(screen.getByRole('table')).queryByText('158')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'all' }));
    expect(within(screen.getByRole('table')).getByText('158')).toBeInTheDocument();
    expect(within(screen.getByRole('table')).queryByText('35')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Download CSV' }));
    const payload = vi.mocked(downloadCsv).mock.calls[0][0];
    expect(payload.rows).toEqual([
      { stage: 'proposed', cohort: 'all', hips: 158, pct: 100 },
      { stage: 'approved', cohort: 'all', hips: 143, pct: 91 },
    ]);
    expect(screen.getByText('Snapshot as of 2026-02-12 12:00 UTC.')).toBeInTheDocument();
  });

  it('renders line and area marks, and normalised shares keep counts in the table', async () => {
    for (const mark of ['line', 'area'] as const) {
      serve({ ...data, mark, id: mark });
      const { unmount } = render(
        <InteractiveChart
          variant={variant(`test/${mark}.json`)}
          title="Marks"
          provenance={provenance}
        />,
      );
      await showData();
      expect(within(screen.getByRole('table')).getByText('20')).toBeInTheDocument();
      unmount();
    }
    serve({ ...repos, normalize: true, rank: false, id: 'shares' });
    render(
      <InteractiveChart
        variant={variant('test/shares.json', 'categories')}
        title="Shares"
        provenance={provenance}
      />,
    );
    await showData();
    expect(within(screen.getByRole('table')).getByText('50')).toBeInTheDocument();
  });

  it('rejects malformed documents before rendering', () => {
    expect(() => validateChartDocument(data)).not.toThrow();
    expect(() => validateChartDocument(repos)).not.toThrow();
    expect(() => validateChartDocument(funnel)).not.toThrow();
    for (const value of [-1, NaN, Infinity, 1.5, '12']) {
      expect(() =>
        validateChartDocument({ ...data, rows: [{ ...data.rows[0], maintainer: value }] }),
      ).toThrow();
    }
    expect(() => validateChartDocument({ ...data, rows: [data.rows[0], data.rows[0]] })).toThrow();
    expect(() =>
      validateChartDocument({ ...repos, rows: [repos.rows[0], repos.rows[0]] }),
    ).toThrow();
    // Stage names repeat across cohorts, but not within one.
    expect(() =>
      validateChartDocument({ ...funnel, rows: [funnel.rows[0], funnel.rows[0]] }),
    ).toThrow();
    expect(() =>
      validateChartDocument({ ...funnel, group: { ...funnel.group!, default: 'none' } }),
    ).toThrow();
    expect(() =>
      validateChartDocument({
        ...data,
        series: [{ ...data.series[0], color: 'red;background:url(x)' }],
      }),
    ).toThrow();
    expect(() => validateChartDocument({ ...data, mark: 'pie' })).toThrow();
    // Decimal documents accept fractional values.
    expect(() =>
      validateChartDocument({
        ...repos,
        value_format: 'decimal',
        rows: [{ ...repos.rows[0], general_user: 7.5 }],
      }),
    ).not.toThrow();
  });
});
