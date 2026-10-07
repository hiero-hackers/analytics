/**
 * Repository and contributor detail views: which names link, the URL they
 * write, Back/Forward, what a view shows (and says it does not measure), the
 * org and tab switches that close one, and the missing, failed and quiet cases.
 */

import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import type { CategoriesDocument } from '../api';
import InteractiveChart from '../components/InteractiveChart';
import {
  directoryOf,
  EntityDirectoryContext,
  entityHash,
  formatEntity,
  parseEntity,
  resetEntityCaches,
} from '../entities';
import { CONTRIBUTOR_INDEX, ENTITY_ROUTES, REPO_DOC, REPOSITORY_INDEX } from './entityFixtures';
import { stubApi } from './stubApi';

const json = (value: unknown) => () => new Response(JSON.stringify(value), { status: 200 });
const entityApi = (overrides: Record<string, () => Response | Promise<Response>> = {}) =>
  stubApi({
    ...Object.fromEntries(
      Object.entries(ENTITY_ROUTES)
        .filter(([path]) => path === 'manifest.json' || path.includes('/entities/'))
        .map(([path, value]) => [path, json(value)]),
    ),
    ...overrides,
  });

beforeEach(() => {
  vi.unstubAllGlobals();
  resetEntityCaches();
  // Recharts measures its container; jsdom has no layout, so report one.
  vi.stubGlobal(
    'ResizeObserver',
    class {
      report: ResizeObserverCallback;
      constructor(report: ResizeObserverCallback) {
        this.report = report;
      }
      observe(target: Element) {
        this.report(
          [{ target, contentRect: { width: 640, height: 340 } } as unknown as ResizeObserverEntry],
          this as never,
        );
      }
      unobserve() {}
      disconnect() {}
    },
  );
  entityApi();
});
afterEach(() => window.history.replaceState(null, '', '/'));

/** Follow a hash change the way a browser does after Back or Forward. */
function goTo(hash: string) {
  act(() => {
    window.history.replaceState(null, '', `/${hash}`);
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  });
}

async function openGovernance() {
  render(<App />);
  await userEvent.click(await screen.findByRole('button', { name: 'Governance' }));
  return await screen.findByRole('region', { name: 'Role holders' });
}

describe('entity URLs', () => {
  it('names a repository or contributor in one hash key, keeping tab, org and focus', () => {
    expect(parseEntity('repo:hiero-sdk-js')).toEqual({ kind: 'repo', id: 'hiero-sdk-js' });
    expect(parseEntity('contributor:alice')).toEqual({ kind: 'contributor', id: 'alice' });
    expect(parseEntity('team:core')).toBeNull();
    expect(parseEntity('repo:')).toBeNull();
    expect(formatEntity({ kind: 'repo', id: '_github' })).toBe('repo:_github');

    window.history.replaceState(
      null,
      '',
      '/#tab=Governance&org=hiero-ledger&focus=repo:x&widget=roles',
    );
    const opened = new URLSearchParams(entityHash({ kind: 'contributor', id: 'alice' }).slice(1));
    expect(Object.fromEntries(opened)).toEqual({
      tab: 'Governance',
      org: 'hiero-ledger',
      focus: 'repo:x',
      entity: 'contributor:alice',
    });
    window.history.replaceState(null, '', `/${entityHash({ kind: 'repo', id: 'x' })}`);
    expect(new URLSearchParams(entityHash(null).slice(1)).has('entity')).toBe(false);
  });
});

describe('Entity links in tables', () => {
  it('opens a listed person’s detail view from a table, keeping a separate GitHub link', async () => {
    const roles = await openGovernance();
    const alice = await within(roles).findByRole('link', { name: /^alice$/ });
    expect(alice).toHaveAttribute('href', expect.stringContaining('entity=contributor%3Aalice'));
    expect(within(roles).getByRole('link', { name: 'alice on GitHub' })).toHaveAttribute(
      'href',
      'https://github.com/alice',
    );
    // carol has no tracked activity: her name still opens the dashboard, which says so.
    expect(within(roles).getByRole('link', { name: /^carol$/ })).toHaveAttribute(
      'href',
      expect.stringContaining('entity=contributor%3Acarol'),
    );
    expect(within(roles).getByRole('link', { name: 'carol on GitHub' })).toHaveAttribute(
      'href',
      'https://github.com/carol',
    );

    goTo(alice.getAttribute('href')!);
    expect(await screen.findByRole('heading', { level: 1, name: 'alice' })).toBeInTheDocument();
    expect(window.location.hash).toContain('tab=Governance');
    expect(screen.getByRole('link', { name: /Back to Governance/ })).toBeInTheDocument();

    // Back returns to the tab; Forward reopens the view.
    goTo('#tab=Governance');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Governance' }),
    ).toBeInTheDocument();
    goTo('#tab=Governance&entity=contributor:alice');
    expect(await screen.findByRole('heading', { level: 1, name: 'alice' })).toBeInTheDocument();
  });
});

describe('Repository detail view', () => {
  it('shows each window’s counts, zeros for a quiet week, and what it does not measure', async () => {
    window.history.replaceState(null, '', '/#tab=Governance&entity=repo:hiero-sdk-js');
    render(<App />);
    expect(
      await screen.findByRole('heading', { level: 1, name: 'hiero-sdk-js' }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/does not measure commits, comments, reactions/),
    ).toBeInTheDocument();
    expect(screen.getByText(/not a measure of individual performance/)).toBeInTheDocument();
    const glance = within(screen.getByRole('region', { name: 'At a glance' }));
    expect(glance.getByText('Tracked actions · 30 days')).toBeInTheDocument();
    expect(glance.getByText('Active contributors')).toBeInTheDocument();

    const periods = within(screen.getByRole('region', { name: 'Activity by period' }));
    const row = (name: string) => periods.getByRole('rowheader', { name }).closest('tr')!;
    const prs = row('PRs opened');
    expect(
      within(prs)
        .getAllByRole('cell')
        .map((cell) => cell.textContent),
    ).toEqual(['0', '3', '11', '40']);
    const active = row('Active contributors');
    expect(within(active).getAllByRole('cell')[0]).toHaveTextContent('0');

    // The activity trend is the dashboard's own chart, with its Data view and CSV.
    const trend = within(screen.getByRole('region', { name: 'Activity over time' }));
    expect(trend.getByRole('radio', { name: 'Data' })).toBeInTheDocument();
    expect(trend.getByRole('button', { name: 'Download CSV' })).toBeInTheDocument();

    // Contributors, with the dashboard's period tabs; a quiet week is an empty table.
    const people = within(screen.getByRole('region', { name: 'Active contributors' }));
    expect(people.getByRole('link', { name: /^alice$/ })).toBeInTheDocument();
    await userEvent.click(people.getByRole('radio', { name: 'Week' }));
    expect(people.queryByRole('link', { name: /^alice$/ })).not.toBeInTheDocument();

    // Related tables that exist are shown; the one this run did not produce is named.
    const releases = within(screen.getByRole('region', { name: 'Releases' }));
    expect(releases.getByText('Days since last release')).toBeInTheDocument();
    expect(releases.getByText('v2.1.0')).toBeInTheDocument();
    expect(
      within(screen.getByRole('region', { name: 'Onboarding' })).getByText(
        'No onboarding data was recorded for this repository.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent('Not available in this data: Security.');

    // Each joined figure links back to the section it summarises, closing the view.
    const source = within(screen.getByRole('region', { name: 'HIP engagement' })).getByRole(
      'link',
      {
        name: /Role holders/,
      },
    );
    const target = new URLSearchParams(source.getAttribute('href')!.slice(1));
    expect([target.get('tab'), target.get('widget'), target.get('entity')]).toEqual([
      'Governance',
      'roles',
      null,
    ]);

    expect(screen.getByRole('link', { name: 'View on GitHub' })).toHaveAttribute(
      'href',
      REPO_DOC.github_url,
    );
    expect(screen.getByText('Count each window from the events inside it.')).toBeInTheDocument();
  });

  it('focuses the dashboard on the repository and returns to the tab in one step', async () => {
    window.history.replaceState(null, '', '/#tab=Governance&entity=repo:hiero-sdk-js');
    render(<App />);
    await userEvent.click(
      await screen.findByRole('button', { name: 'Focus the dashboard on hiero-sdk-js' }),
    );
    await waitFor(() => expect(window.location.hash).not.toContain('entity='));
    expect(new URLSearchParams(window.location.hash.slice(1)).get('focus')).toBe(
      'repo:hiero-sdk-js',
    );
    expect(await screen.findByRole('region', { name: 'Dashboard focus' })).toBeInTheDocument();
  });

  it('shows a short related list first and lets the reader reveal the rest', async () => {
    const many = Array.from({ length: 12 }, (_, index) => ({ tag_name: `v${index}` }));
    const document = {
      ...REPO_DOC,
      related: REPO_DOC.related.map((section) =>
        section.id === 'releases' && section.list
          ? { ...section, list: { ...section.list, rows: many } }
          : section,
      ),
    };
    entityApi({ 'hiero-ledger/entities/repositories/hiero-sdk-js.json': json(document) });
    window.history.replaceState(null, '', '/#entity=repo:hiero-sdk-js');
    render(<App />);
    const releases = within(await screen.findByRole('region', { name: 'Releases' }));
    expect(releases.getByText('v7')).toBeInTheDocument();
    expect(releases.queryByText('v8')).not.toBeInTheDocument();
    await userEvent.click(releases.getByRole('button', { name: 'Show all 12' }));
    expect(releases.getByText('v11')).toBeInTheDocument();
    await userEvent.click(releases.getByRole('button', { name: 'Show fewer' }));
    expect(releases.queryByText('v8')).not.toBeInTheDocument();
  });
});

describe('Contributor detail view', () => {
  it('lists the repositories touched with their activity and links each one', async () => {
    window.history.replaceState(null, '', '/#tab=Contributors&entity=contributor:alice');
    render(<App />);
    expect(await screen.findByRole('heading', { level: 1, name: 'alice' })).toBeInTheDocument();
    expect(await screen.findByText(/Tracked since 2024-03-01/)).toBeInTheDocument();
    const repos = within(screen.getByRole('region', { name: 'Repositories' }));
    expect(repos.getByRole('link', { name: 'hiero-ledger/hiero-sdk-js' })).toHaveAttribute(
      'href',
      expect.stringContaining('entity=repo%3Ahiero-sdk-js'),
    );
    // hiero-docs has no index entry, but its name still opens the dashboard like every other.
    expect(repos.getByRole('link', { name: 'hiero-ledger/hiero-docs' })).toHaveAttribute(
      'href',
      expect.stringContaining('entity=repo%3Ahiero-docs'),
    );
    const mix = within(screen.getByRole('region', { name: 'Activity by period' }));
    expect(mix.getByRole('row', { name: /Repositories touched/ })).toBeInTheDocument();
    expect(
      within(mix.getByRole('row', { name: /Building & fixing/ })).getAllByRole('cell')[3],
    ).toHaveTextContent('73%');
    expect(screen.getByRole('region', { name: 'Activity over time' })).toHaveTextContent(
      'No monthly activity was recorded.',
    );
  });
});

describe('Leaving and missing detail views', () => {
  it('closes the view when the reader picks a tab or switches organisation', async () => {
    window.history.replaceState(
      null,
      '',
      '/#tab=Governance&entity=contributor:alice&focus=contributor:alice',
    );
    render(<App />);
    await screen.findByRole('heading', { level: 1, name: 'alice' });
    await userEvent.click(screen.getByRole('button', { name: 'Contributors' }));
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Contributors' }),
    ).toBeInTheDocument();
    const params = new URLSearchParams(window.location.hash.slice(1));
    expect([params.get('tab'), params.get('entity'), params.get('focus')]).toEqual([
      'Contributors',
      null,
      'contributor:alice',
    ]);

    goTo('#tab=Governance&entity=contributor:alice&focus=contributor:alice');
    await screen.findByRole('heading', { level: 1, name: 'alice' });
    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: 'Organisation' }),
      'hiero-hackers',
    );
    await waitFor(() => expect(window.location.hash).not.toContain('entity='));
    expect(window.location.hash).not.toContain('focus=');
  });

  it('explains a name with no tracked activity instead of showing an empty page', async () => {
    window.history.replaceState(null, '', '/#tab=Governance&entity=contributor:nobody');
    render(<App />);
    expect(
      await screen.findByText('No tracked activity for nobody in hiero-ledger'),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View on GitHub' })).toHaveAttribute(
      'href',
      'https://github.com/nobody',
    );
  });

  it('offers a retry when a detail document fails to load', async () => {
    let fail = true;
    entityApi({
      'hiero-ledger/entities/repositories/hiero-sdk-js.json': () =>
        fail ? new Response('down', { status: 503 }) : new Response(JSON.stringify(REPO_DOC)),
    });
    window.history.replaceState(null, '', '/#tab=Governance&entity=repo:hiero-sdk-js');
    render(<App />);
    expect(
      await screen.findByText('Could not load the details for hiero-sdk-js.'),
    ).toBeInTheDocument();
    fail = false;
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('region', { name: 'Activity by period' })).toBeInTheDocument();
  });
});

describe('Entity links in charts', () => {
  const ranking: CategoriesDocument = {
    schema_version: 1,
    id: 'by-repo',
    org: 'hiero-ledger',
    kind: 'categories',
    source: 'by_repo.csv',
    metric: 'actions',
    unit: 'Tracked actions',
    population: 'Every repository.',
    dimensions: ['repo'],
    mark: 'bar',
    stacked: false,
    normalize: false,
    orientation: 'horizontal',
    value_format: 'integer',
    rank: true,
    top_n: null,
    reference: null,
    group: null,
    category: { key: 'repo', label: 'Repository' },
    window: { kind: 'all', days: null, end: '2026-07-25T10:00:00+00:00' },
    series: [{ key: 'count', label: 'Actions', color: 'var(--chart-1)' }],
    details: [],
    rows: [
      { repo: 'hiero-sdk-js', count: 9 },
      { repo: 'hiero-unlisted', count: 4 },
    ],
  };
  const directory = directoryOf('hiero-ledger', REPOSITORY_INDEX, CONTRIBUTOR_INDEX);

  it('links names on the axis and in the Data view, keeping the focus control', async () => {
    stubApi({ 'charts/by-repo.json': json(ranking) });
    render(
      <EntityDirectoryContext.Provider value={directory}>
        <InteractiveChart
          variant={{
            label: 'All time',
            interactive: { kind: 'categories', path: 'charts/by-repo.json' },
          }}
          title="Actions by repository"
          provenance={{ git_sha: null, data_as_of: null }}
        />
      </EntityDirectoryContext.Provider>,
    );
    const tick = await screen.findByRole('link', { name: 'Open the details for hiero-sdk-js' });
    expect(tick).toHaveAttribute('href', expect.stringContaining('entity=repo%3Ahiero-sdk-js'));
    // A repository with no index entry links too; its view says it has no tracked activity.
    expect(
      screen.getByRole('link', { name: 'Open the details for hiero-unlisted' }),
    ).toHaveAttribute('href', expect.stringContaining('entity=repo%3Ahiero-unlisted'));

    await userEvent.click(screen.getByRole('radio', { name: 'Data' }));
    const table = within(screen.getByRole('table'));
    expect(table.getByRole('link', { name: 'hiero-sdk-js' })).toBeInTheDocument();
    // The focus toggles from a crosshair beside each name.
    await userEvent.click(table.getByRole('button', { name: 'Focus on hiero-sdk-js' }));
    expect(new URLSearchParams(window.location.hash.slice(1)).get('focus')).toBe(
      'repo:hiero-sdk-js',
    );
    expect(table.getByRole('link', { name: 'hiero-unlisted' })).toBeInTheDocument();
    expect(table.getByRole('button', { name: 'Focus on hiero-unlisted' })).toBeInTheDocument();
  });
});

describe('Unavailable entity indexes', () => {
  it('never reports "no tracked activity" from an index that failed to load, and retries it', async () => {
    let fail = true;
    entityApi({
      'hiero-ledger/entities/contributors.json': () =>
        fail ? new Response('down', { status: 503 }) : json(CONTRIBUTOR_INDEX)(),
    });
    window.history.replaceState(null, '', '/#tab=Governance&entity=contributor:alice');
    render(<App />);
    expect(
      await screen.findByText('Could not load the contributor details for hiero-ledger.'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/No tracked activity for alice/)).not.toBeInTheDocument();

    fail = false;
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('region', { name: 'Activity by period' })).toBeInTheDocument();
  });

  it('keeps names of a kind whose index failed as plain GitHub links', async () => {
    entityApi({
      'hiero-ledger/entities/contributors.json': () => new Response('down', { status: 503 }),
    });
    const roles = await openGovernance();
    expect(within(roles).getByRole('link', { name: /^alice$/ })).toHaveAttribute(
      'href',
      'https://github.com/alice',
    );
    expect(within(roles).queryByRole('link', { name: 'alice on GitHub' })).not.toBeInTheDocument();
  });

  it('explains an organisation that publishes no detail views instead of loading forever', async () => {
    window.history.replaceState(
      null,
      '',
      '/#tab=Contributors&org=hiero-hackers&entity=contributor:alice',
    );
    render(<App />);
    expect(
      await screen.findByText('No contributor detail views are published for hiero-hackers'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('status', { name: 'Loading details' })).not.toBeInTheDocument();
  });
});
