import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import InteractiveChart from '../components/InteractiveChart';
import { shade } from '../components/charts/format';
import { validateChartDocument } from '../chartData';
import { downloadCsv } from '../csv';
import type {
  ChartDocument,
  ChartVariant,
  EventsDocument,
  MatrixDocument,
  NetworkDocument,
} from '../api';

vi.mock('../csv', () => ({ downloadCsv: vi.fn() }));

const meta = {
  schema_version: 1 as const,
  org: 'test',
  source: 'source.csv',
  metric: 'metric',
  population: 'Who is counted.',
  generated_at: '2026-09-07T12:00:00Z',
};
const heatmap: MatrixDocument = {
  ...meta,
  id: 'heat',
  kind: 'matrix',
  unit: 'Weighted monthly activity score',
  dimensions: ['contributor name', 'column'],
  row: { key: 'contributor name', label: 'Contributor' },
  sublabel: { key: 'role', label: 'Highest role' },
  total: { key: 'activity score', label: 'Six-month score' },
  columns: [
    { key: '2026-07', label: '2026-07' },
    { key: '2026-08', label: '2026-08' },
  ],
  value_label: 'Weighted activity score',
  scale: { min: 0, max: 100, steps: 5 },
  missing: null,
  avatars: true,
  top_n: 2,
  value_format: 'integer',
  window: { kind: 'snapshot', days: null, end: '2026-09-07T12:00:00Z' },
  rows: [
    {
      'contributor name': 'ann',
      role: 'Maintainer',
      'activity score': 150,
      '2026-07': 100,
      '2026-08': 50,
    },
    {
      'contributor name': 'bo',
      role: 'Committer',
      'activity score': 30,
      '2026-07': 0,
      '2026-08': 30,
    },
    { 'contributor name': 'cy', role: '', 'activity score': 5, '2026-07': 5, '2026-08': 0 },
  ],
};
const checks: MatrixDocument = {
  ...heatmap,
  id: 'checks',
  unit: 'OpenSSF Scorecard check scores',
  row: { key: 'repo', label: 'Repository' },
  sublabel: null,
  total: { key: 'score', label: 'Aggregate score' },
  columns: [
    { key: 'Maintained', label: 'Maintained' },
    { key: 'Fuzzing', label: 'Fuzzing' },
  ],
  scale: { min: 0, max: 10, steps: 5 },
  missing: 'Not scored',
  avatars: false,
  top_n: null,
  value_format: 'decimal',
  rows: [{ repo: 'sdk', score: 6.4, Maintained: 10, Fuzzing: null }],
};
const network: NetworkDocument = {
  ...meta,
  id: 'net',
  kind: 'network',
  unit: 'Repositories linked by shared maintainers',
  dimensions: ['repository', 'link'],
  member_label: 'maintainers',
  categories: [
    { key: 'SDKs', label: 'SDKs', color: '#0EA5E9' },
    { key: 'Governance', label: 'Governance', color: '#EF4444' },
  ],
  window: { kind: 'snapshot', days: null, end: null },
  nodes: [
    { id: 'hiero-sdk-js', active: 3, total: 4, category: 'SDKs', x: -1, y: 0 },
    { id: 'hiero-sdk-go', active: 1, total: 2, category: 'SDKs', x: 1, y: 0 },
    { id: 'hiero-sdk-rust', active: 1, total: 1, category: 'SDKs', x: 0, y: 1 },
    { id: 'governance', active: 0, total: 1, category: 'Governance', x: 0, y: -2 },
  ],
  edges: [
    { source: 'hiero-sdk-js', target: 'hiero-sdk-go', shared: 2 },
    { source: 'hiero-sdk-go', target: 'hiero-sdk-rust', shared: 1 },
  ],
};
const releases: EventsDocument = {
  ...meta,
  id: 'releases',
  kind: 'events',
  unit: 'Published releases',
  dimensions: ['repo', 'type'],
  category: { key: 'repo', label: 'Repository' },
  label: { key: 'tag_name', label: 'Tag' },
  types: [
    { key: 'release', label: 'Release', color: 'var(--chart-2)' },
    { key: 'prerelease', label: 'Prerelease', color: 'var(--chart-1)' },
  ],
  categories: ['sdk-js', 'sdk-go'],
  window: { kind: 'trailing', days: 30, end: '2026-09-07T12:00:00Z' },
  rows: [
    { repo: 'sdk-js', time: '2026-08-20T10:00:00Z', tag_name: 'v2.0.0-rc1', type: 'prerelease' },
    { repo: 'sdk-go', time: '2026-08-25T10:00:00Z', tag_name: 'v1.4.0', type: 'release' },
    { repo: 'sdk-js', time: '2026-09-01T10:00:00Z', tag_name: 'v2.0.0', type: 'release' },
  ],
};
const provenance = { git_sha: 'abc', data_as_of: null };
const variant = (document: ChartDocument, label = 'View'): ChartVariant => ({
  label,
  file: 'legacy.png',
  image_available: false,
  interactive: { kind: document.kind, path: `test/${document.id}.json` },
});
function show(document: ChartDocument, title = 'Chart') {
  vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => document } as Response);
  return render(
    <InteractiveChart variant={variant(document, title)} title={title} provenance={provenance} />,
  );
}
const cells = () =>
  screen
    .getAllByRole('row')
    .slice(1)
    .map((row) => row.querySelector('td, th')?.textContent);

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
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('Heatmap matrix', () => {
  it('colours on the declared linear scale and keeps missing values distinct', () => {
    const scale = { min: 0, max: 100, steps: 5 };
    expect([0, 1, 20, 21, 100, 250].map((value) => shade(value, scale))).toEqual([
      0, 1, 1, 2, 5, 5,
    ]);
    expect(shade(null, scale)).toBeNull();
  });

  it('shows the top rows, reveals every match on search, and exports what is shown', async () => {
    show(heatmap, 'Heatmap');
    const grid = await screen.findByRole('grid');
    expect(within(grid).getAllByRole('row')).toHaveLength(3); // header + top 2
    expect(within(grid).getByRole('link', { name: /ann/ })).toHaveAttribute(
      'href',
      'https://github.com/ann',
    );
    expect(screen.getByText('Maintainer')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Show all 3 contributors' }));
    expect(within(grid).getAllByRole('row')).toHaveLength(4);
    await userEvent.type(screen.getByRole('textbox', { name: 'Search contributors' }), 'cy');
    expect(within(screen.getByRole('grid')).getAllByRole('row')).toHaveLength(2);
    await userEvent.click(screen.getByRole('button', { name: 'Download CSV' }));
    const payload = vi.mocked(downloadCsv).mock.calls[0][0];
    expect(payload.rows).toEqual([
      { 'contributor name': 'cy', role: '', '2026-07': 5, '2026-08': 0, 'activity score': 5 },
    ]);
  });

  it('is one tab stop, moves with the arrow keys, and reads out the focused cell', async () => {
    show(heatmap, 'Heatmap');
    const grid = await screen.findByRole('grid');
    const gridcells = within(grid).getAllByRole('gridcell');
    expect(gridcells.filter((cell) => cell.tabIndex === 0)).toHaveLength(1);
    act(() => gridcells[0].focus());
    expect(screen.getByText(/ann, Jul 26: 100 \(weighted activity score\)/)).toBeInTheDocument();
    fireEvent.keyDown(gridcells[0], { key: 'ArrowRight' });
    expect(gridcells[1]).toHaveFocus();
    fireEvent.keyDown(gridcells[1], { key: 'ArrowDown' });
    expect(gridcells[3]).toHaveFocus();
    expect(screen.getByText(/bo, Aug 26: 30/)).toBeInTheDocument();
  });

  it('labels unscored checks instead of colouring them as zero', async () => {
    show(checks, 'Checks');
    const grid = await screen.findByRole('grid');
    expect(
      within(grid).getByRole('gridcell', { name: 'sdk, Fuzzing: Not scored' }),
    ).toHaveTextContent('?');
    expect(within(grid).getByRole('gridcell', { name: 'sdk, Maintained: 10' })).toHaveStyle({
      backgroundColor: 'var(--heat-5)',
    });
    expect(screen.getByText('? Not scored')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'Data' }));
    expect(within(screen.getByRole('table')).getByText('Not scored')).toBeInTheDocument();
  });
});

describe('Network', () => {
  it('selects a repository, highlights its links, and narrows the data to them', async () => {
    show(network, 'Network');
    const js = await screen.findByRole('button', {
      name: 'hiero-sdk-js, SDKs: 3 active maintainers, linked to 1 repository',
    });
    expect(screen.getByText('not linked — no shared maintainers')).toBeInTheDocument();
    await userEvent.click(js);
    expect(js).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: /sdk-go\s*2 shared/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'Data' }));
    expect(cells()).toEqual(['hiero-sdk-js', 'hiero-sdk-go']);
    expect(within(screen.getByRole('table')).getByText('hiero-sdk-go (2)')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Download CSV' }));
    expect(vi.mocked(downloadCsv).mock.calls[0][0].rows.map((row) => row.repo)).toEqual([
      'hiero-sdk-js',
      'hiero-sdk-go',
    ]);
  });

  it('opens a node from the keyboard and follows a link from the neighbour list', async () => {
    show(network, 'Network');
    const go = await screen.findByRole('button', { name: /^hiero-sdk-go, SDKs/ });
    act(() => go.focus());
    await userEvent.keyboard('{Enter}');
    expect(go).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(screen.getByRole('button', { name: /sdk-rust\s*1 shared/ }));
    expect(screen.getByRole('button', { name: /^hiero-sdk-rust, SDKs/ })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await userEvent.click(screen.getByRole('button', { name: 'Zoom in' }));
    await userEvent.click(screen.getByRole('button', { name: 'Reset view' }));
  });

  it('search narrows the data view to matching repositories', async () => {
    show(network, 'Network');
    await userEvent.type(await screen.findByRole('textbox', { name: 'Find a repository' }), 'gov');
    await userEvent.click(screen.getByRole('radio', { name: 'Data' }));
    expect(cells()).toEqual(['governance']);
  });
});

describe('Release timeline', () => {
  it('lists releases newest first and hides a type from table and CSV together', async () => {
    show(releases, 'Releases');
    await userEvent.click(await screen.findByRole('radio', { name: 'Data' }));
    expect(cells()).toEqual(['2026-09-01 10:00', '2026-08-25 10:00', '2026-08-20 10:00']);
    await userEvent.click(screen.getByRole('button', { name: 'Prerelease' }));
    expect(cells()).toHaveLength(2);
    await userEvent.click(screen.getByRole('button', { name: 'Download CSV' }));
    const payload = vi.mocked(downloadCsv).mock.calls[0][0];
    expect(payload.rows.map((row) => row.tag_name)).toEqual(['v2.0.0', 'v1.4.0']);
    expect(payload.rows[0].type).toBe('Release');
    expect(
      screen.getByText('Window: the 30 days before 2026-09-07 12:00 UTC.'),
    ).toBeInTheDocument();
  });

  it('says so when the window has no releases', async () => {
    // A distinct id: documents are cached by path.
    show({ ...releases, id: 'quiet', rows: [], categories: [] }, 'Releases');
    expect(
      await screen.findByText('No releases were published in this window.'),
    ).toBeInTheDocument();
  });
});

describe('Validation of specialised documents', () => {
  it('accepts well-formed documents and rejects broken references', () => {
    for (const document of [heatmap, checks, network, releases]) {
      expect(() => validateChartDocument(document)).not.toThrow();
    }
    expect(() =>
      validateChartDocument({ ...heatmap, rows: [heatmap.rows[0], heatmap.rows[0]] }),
    ).toThrow();
    expect(() =>
      validateChartDocument({ ...heatmap, rows: [{ ...heatmap.rows[0], '2026-07': -3 }] }),
    ).toThrow();
    expect(() =>
      validateChartDocument({
        ...network,
        edges: [{ source: 'hiero-sdk-js', target: 'nowhere', shared: 1 }],
      }),
    ).toThrow();
    expect(() =>
      validateChartDocument({
        ...network,
        edges: [...network.edges, { source: 'hiero-sdk-go', target: 'hiero-sdk-js', shared: 2 }],
      }),
    ).toThrow();
    expect(() =>
      validateChartDocument({
        ...network,
        categories: [{ ...network.categories[0], color: 'red' }],
      }),
    ).toThrow();
    expect(() =>
      validateChartDocument({ ...releases, rows: [{ ...releases.rows[0], type: 'draft' }] }),
    ).toThrow();
    expect(() =>
      validateChartDocument({ ...releases, rows: [{ ...releases.rows[0], repo: 'unlisted' }] }),
    ).toThrow();
  });
});
