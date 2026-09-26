import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { CategoriesDocument, ChartVariant, SectionDoc, TimeseriesDocument } from '../api';
import InteractiveChart from '../components/InteractiveChart';
import { FocusBar } from '../components/FocusBar';
import { SectionTable } from '../components/SectionTable';
import { normalise } from '../focus';
import { readParam, writeParams } from '../urlState';

vi.mock('../csv', () => ({ downloadCsv: vi.fn(), downloadCsvText: vi.fn() }));

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
    { key: 'committer', label: 'Committers', color: 'var(--chart-committer)' },
    { key: 'maintainer', label: 'Maintainers', color: 'var(--chart-maintainer)' },
  ],
};
const monthly: TimeseriesDocument = {
  ...shared,
  id: 'monthly',
  kind: 'timeseries',
  dimensions: ['period', 'series'],
  frequency: 'month',
  timezone: 'UTC',
  comparison: { current: '2026-02', previous: '2026-01' },
  group: null,
  category: { key: 'bucket', label: 'Period (UTC)' },
  window: { kind: 'calendar', first: '2026-01', last: '2026-03' },
  rows: [
    { bucket: '2026-01', committer: 10, maintainer: 4, partial: false },
    { bucket: '2026-02', committer: 12, maintainer: 4, partial: false },
    { bucket: '2026-03', committer: 1, maintainer: 1, partial: true },
  ],
};
const byRepo: CategoriesDocument = {
  ...shared,
  id: 'byrepo',
  kind: 'categories',
  dimensions: ['repo', 'series'],
  orientation: 'horizontal',
  rank: true,
  top_n: 1,
  group: null,
  category: { key: 'repo', label: 'Repository' },
  window: { kind: 'all', days: null, end: null },
  rows: [
    { repo: 'hiero-sdk-js', committer: 9, maintainer: 3 },
    { repo: 'hiero-sdk-go', committer: 2, maintainer: 1 },
  ],
};
const table: SectionDoc = {
  id: 'repoactivity',
  title: 'Repository activity',
  description: 'Per repository.',
  group: 'Activity',
  macro: 'Governance',
  source: 'repo_activity_overview.csv',
  columns: [
    { key: 'repo', label: 'Repository' },
    { key: 'prs', label: 'PRs', format: 'number' },
  ],
  rows: [
    { repo: 'hiero-ledger/hiero-sdk-js', prs: 40 },
    { repo: 'hiero-ledger/hiero-sdk-go', prs: 12 },
    { repo: 'hiero-ledger/hiero-cli', prs: 3 },
  ],
  row_count: 3,
};
const people: SectionDoc = {
  ...table,
  id: 'people',
  title: 'People',
  columns: [{ key: 'login', label: 'Login' }],
  rows: [{ login: 'ann' }, { login: 'bo' }],
  row_count: 2,
};
const provenance = { git_sha: 'abc', data_as_of: null };
const variant = (id: string, kind: 'timeseries' | 'categories'): ChartVariant => ({
  label: 'View',
  file: 'legacy.png',
  image_available: false,
  interactive: { kind, path: `test/${id}.json` },
});
const serve = (...documents: unknown[]) => {
  for (const document of documents) {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => document } as Response);
  }
};
const bodyRows = (element: HTMLElement) => within(element).getAllByRole('row').slice(1);

beforeEach(() => {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  vi.stubGlobal('fetch', vi.fn());
  window.history.replaceState(null, '', '/');
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('URL state', () => {
  it('rewrites the current entry for view state and drops defaults', () => {
    const before = window.history.length;
    writeParams({ tab: 'Governance' }, { push: true });
    writeParams({ 'monthly.view': '1', 'monthly.q': 'abc' });
    writeParams({ 'monthly.q': '' });
    expect(window.history.length).toBe(before + 1);
    expect(window.location.hash).toBe('#tab=Governance&monthly.view=1');
    expect(readParam('monthly.q', 'none')).toBe('none');
  });

  it('reopens a shared link with the same view, hidden series and all', async () => {
    window.history.replaceState(null, '', '/#monthly.view=1&monthly.hide=maintainer');
    serve(monthly);
    render(
      <InteractiveChart
        variant={variant('monthly', 'timeseries')}
        title="Roles"
        provenance={provenance}
      />,
    );
    const data = await screen.findByRole('table');
    expect(screen.getByRole('button', { name: 'Maintainers' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
    expect(
      within(data).queryByRole('columnheader', { name: 'Maintainers' }),
    ).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Maintainers' }));
    expect(window.location.hash).toBe('#monthly.view=1');
  });
});

describe('Previous-period comparison', () => {
  it('compares the last complete buckets named by the exporter, never the partial one', async () => {
    serve(monthly);
    render(
      <InteractiveChart
        variant={variant('monthly-cmp', 'timeseries')}
        title="Roles"
        provenance={provenance}
      />,
    );
    expect(await screen.findByText(/Feb 26 compared with Jan 26/)).toHaveTextContent(
      'incomplete current bucket is left out',
    );
    expect(screen.getByLabelText('up 2 from 10')).toHaveTextContent('(+2, +20%)');
    expect(screen.getByLabelText('no change from 4')).toHaveTextContent('(±0, ±0%)');
  });

  it('shows no comparison when the exporter supplies none', async () => {
    serve({ ...monthly, id: 'nocmp', comparison: null });
    render(
      <InteractiveChart
        variant={variant('nocmp', 'timeseries')}
        title="Roles"
        provenance={provenance}
      />,
    );
    await screen.findByRole('radio', { name: 'Data' });
    expect(screen.queryByText(/compared with/)).not.toBeInTheDocument();
  });
});

describe('Focus', () => {
  it('normalises owner prefixes and case so charts and tables agree', () => {
    expect(normalise('repo', 'Hiero-Ledger/Hiero-SDK-JS')).toBe('hiero-sdk-js');
    expect(normalise('contributor', 'Ann')).toBe('ann');
  });

  it('flows from a chart to the tables that have that column, and only those', async () => {
    serve(byRepo, monthly);
    render(
      <>
        <FocusBar />
        <InteractiveChart
          variant={variant('byrepo', 'categories')}
          title="By repo"
          provenance={provenance}
        />
        <InteractiveChart
          variant={variant('monthly-focus', 'timeseries')}
          title="Over time"
          provenance={provenance}
        />
        <SectionTable doc={table} provenance={provenance} />
        <SectionTable doc={people} provenance={provenance} />
      </>,
    );
    await screen.findAllByRole('radio', { name: 'Data' });
    await userEvent.click(screen.getAllByRole('radio', { name: 'Data' })[0]);
    await userEvent.click(screen.getByRole('button', { name: 'Focus on hiero-sdk-go' }));
    expect(window.location.hash).toBe('#byrepo.view=1&focus=repo%3Ahiero-sdk-go');

    expect(screen.getByRole('region', { name: 'Dashboard focus' })).toHaveTextContent(
      'Focused on repository hiero-sdk-go',
    );
    // The repository table narrows and says so; the per-person table is untouched.
    expect(screen.getByText(/1 of 3 rows/)).toBeInTheDocument();
    const repoTable = screen.getByText('hiero-ledger/hiero-sdk-go').closest('table')!;
    expect(bodyRows(repoTable)).toHaveLength(1);
    const peopleTable = screen.getByText('bo').closest('table')!;
    expect(bodyRows(peopleTable)).toHaveLength(2);
    // The monthly chart has no repository breakdown, and says it is organisation-wide.
    expect(
      screen.getByText(/Shows the whole organisation: this chart has no repository breakdown/),
    ).toBeInTheDocument();
    // The focused row stays in the chart's data view even beyond its top 1.
    expect(screen.getByRole('button', { name: 'Focus on hiero-sdk-go' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );

    const bar = screen.getByRole('region', { name: 'Dashboard focus' });
    await userEvent.click(within(bar).getByRole('button', { name: 'Clear focus' }));
    expect(screen.queryByRole('region', { name: 'Dashboard focus' })).not.toBeInTheDocument();
    expect(bodyRows(screen.getByText('hiero-ledger/hiero-sdk-go').closest('table')!)).toHaveLength(
      3,
    );
  });

  it('applies a focus arriving in a shared link and follows Back/forward', async () => {
    window.history.replaceState(null, '', '/#focus=repo:hiero-cli');
    render(<SectionTable doc={table} provenance={provenance} />);
    expect(screen.getByText(/1 of 3 rows/)).toBeInTheDocument();
    act(() => {
      window.history.replaceState(null, '', '/#focus=repo:hiero-sdk-js');
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    });
    expect(screen.getByText('hiero-ledger/hiero-sdk-js')).toBeInTheDocument();
    expect(screen.queryByText('hiero-ledger/hiero-cli')).not.toBeInTheDocument();
  });

  it('notes when a chart has the dimension but not the focused value', async () => {
    window.history.replaceState(null, '', '/#focus=repo:elsewhere');
    serve(byRepo);
    render(
      <InteractiveChart
        variant={variant('byrepo-missing', 'categories')}
        title="By repo"
        provenance={provenance}
      />,
    );
    expect(await screen.findByText('elsewhere does not appear in this chart.')).toBeInTheDocument();
  });
});
