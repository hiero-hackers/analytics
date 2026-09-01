/**
 * App-level behaviour against the fixture manifest: macro tabs, per-macro org
 * tabs, metric tiles, glossary, section groups, and the table chrome
 * (sorting, filtering, period tabs, the action link).
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { stubApi } from './fixtures';

beforeEach(() => {
  vi.unstubAllGlobals();
  stubApi();
});

const openGovernance = async () => {
  render(<App />);
  await screen.findByRole('button', { name: 'Governance' });
  await userEvent.click(screen.getByRole('button', { name: 'Governance' }));
  return await screen.findByText('Role holders');
};

describe('App shell', () => {
  it('renders a macro tab per manifest macro and switches between them', async () => {
    render(<App />);

    expect(await screen.findByRole('button', { name: 'Governance' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Contributors' })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Governance' }));
    expect(await screen.findByText('Role holders')).toBeInTheDocument();
    expect(screen.getByText('Maintainer pipeline')).toBeInTheDocument();
  });

  it('keeps the org filter global and sticky, explaining tabs the org lacks', async () => {
    render(<App />);

    // The org filter is present on every tab.
    await userEvent.click(await screen.findByRole('button', { name: 'Contributors' }));
    expect(await screen.findByRole('button', { name: 'hiero-hackers' })).toBeInTheDocument();

    // Select hiero-hackers, then open Governance: the selection sticks, and
    // the tab explains why this org has no governance content.
    await userEvent.click(screen.getByRole('button', { name: 'hiero-hackers' }));
    await screen.findByText('erin');
    await userEvent.click(screen.getByRole('button', { name: 'Governance' }));
    expect(await screen.findByText(/need a published governance config/)).toBeInTheDocument();
    expect(screen.queryByText('Role holders')).not.toBeInTheDocument();

    // Switching back to hiero-ledger restores the tab's content.
    await userEvent.click(screen.getByRole('button', { name: 'hiero-ledger' }));
    expect(await screen.findByText('Role holders')).toBeInTheDocument();
  });

  it('switching org swaps the rendered rows', async () => {
    render(<App />);
    await userEvent.click(await screen.findByRole('button', { name: 'Contributors' }));
    expect(await screen.findByText('alice')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'hiero-hackers' }));
    expect(await screen.findByText('erin')).toBeInTheDocument();
    expect(screen.queryByText('alice')).not.toBeInTheDocument();
  });

  it('renders metric tiles, the glossary, group headers, and both footers', async () => {
    await openGovernance();

    expect(screen.getByText('maintainers')).toBeInTheDocument();
    expect(screen.getByText('103')).toBeInTheDocument();
    expect(screen.getByText('How to read this — what each column means')).toBeInTheDocument();
    // Each group appears twice: once in the jump bar (a button — deliberately
    // not a fragment link, which would clobber the tab/org hash state), once
    // as its header. The chart card renders under its own named group — there
    // is no generic "Charts" section any more.
    expect(screen.getByRole('button', { name: 'Pipeline charts' })).toBeInTheDocument();
    expect(screen.getAllByText('Pipeline charts')).toHaveLength(2);
    expect(screen.queryByText('Charts')).not.toBeInTheDocument();
    expect(screen.getAllByText('Roles & teams')).toHaveLength(2);
    expect(screen.getByText(/Work in progress/)).toBeInTheDocument();
    // The footer is the general "something looks wrong" route: only the
    // affiliations table carries a contextual correction link, so pointing
    // readers at "a table's link" left most tabs with no way to report.
    expect(screen.getByRole('link', { name: 'Open an issue' })).toHaveAttribute(
      'href',
      'https://example.test/issues',
    );
    expect(screen.getByText(/data 2026-07-25 21:00 UTC · code abc1234/)).toBeInTheDocument();
  });
});

describe('Section tables', () => {
  it('sorts by a clicked column header', async () => {
    await openGovernance();
    const table = screen.getByRole('table');

    // Numeric columns sort descending first (TanStack default), then toggle.
    await userEvent.click(within(table).getByText('count'));
    let users = within(table)
      .getAllByRole('row')
      .slice(1)
      .map((row) => within(row).getAllByRole('cell')[0].textContent);
    expect(users).toEqual(['alice', 'bob', 'carol']);

    await userEvent.click(within(table).getByText(/count/));
    users = within(table)
      .getAllByRole('row')
      .slice(1)
      .map((row) => within(row).getAllByRole('cell')[0].textContent);
    expect(users).toEqual(['carol', 'bob', 'alice']);
  });

  it('filters rows and shows the shown-of-total badge', async () => {
    await openGovernance();

    await userEvent.type(screen.getByPlaceholderText('Filter…'), 'ali');
    expect(screen.getByText('1 of 3')).toBeInTheDocument();
    expect(screen.queryByText('bob')).not.toBeInTheDocument();
  });

  it('period tabs swap the row set', async () => {
    await openGovernance();
    expect(screen.getByText('bob')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '1 month' }));
    expect(screen.queryByText('bob')).not.toBeInTheDocument();
    expect(screen.getByText('alice')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'All time' }));
    expect(screen.getByText('bob')).toBeInTheDocument();
  });

  it('formats number columns with separators and tabular figures', async () => {
    await openGovernance();

    const cell = screen.getByText('2,490'); // 2490 renders with a separator
    // Cells centre by default; `num` is what earns a column tabular digits.
    expect(cell.closest('td')).toHaveClass('num');
    const table = screen.getByRole('table');
    expect(within(table).getByText('count').closest('th')).toHaveClass('num');
  });

  it('offers the period windows shortest-first, with all time last', async () => {
    await openGovernance();

    const tabs = within(screen.getByRole('group', { name: 'Time range' })).getAllByRole('button');

    expect(tabs.map((tab) => tab.textContent)).toEqual(['1 month', 'All time']);
  });

  it('renders date formats, the freshness badge, and the action link', async () => {
    await openGovernance();

    expect(screen.getByText('2026-07-20')).toBeInTheDocument(); // date format trims time
    expect(screen.getByText(/data as of 2026-07-25 10:00/)).toBeInTheDocument();
    const action = screen.getByRole('link', { name: 'Suggest a correction' });
    expect(action).toHaveAttribute('href', 'https://example.test/correct');
  });
});

describe('Charts', () => {
  it('renders variant tabs and opens the lightbox with note and methodology', async () => {
    await openGovernance();

    expect(screen.getByRole('button', { name: 'By year' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'By month' })).toBeInTheDocument();

    await userEvent.click(screen.getByAltText('Unique active contributors by role'));
    const lightbox = await screen.findByRole('dialog');
    expect(within(lightbox).getByText('How to read this chart.')).toBeInTheDocument();
    expect(within(lightbox).getByText('Step-by-step methodology')).toBeInTheDocument();
    expect(within(lightbox).getByText('Step two.')).toBeInTheDocument();

    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

describe('Organisation diversity card (#435)', () => {
  const openDiversity = async () => {
    render(<App />);
    await screen.findByRole('button', { name: 'Diversity' });
    await userEvent.click(screen.getByRole('button', { name: 'Diversity' }));
    return await screen.findByText('Organisation diversity');
  };

  const chartSrc = (title: string) => screen.getByAltText(title).getAttribute('src');

  it('gives the card one role axis, so every role-tabbed chart switches together', async () => {
    await openDiversity();

    // One tab row for the card, not one per chart: three charts, two of which
    // share the axis, must not be able to disagree about the active role.
    const axes = screen.getAllByRole('group', { name: 'Organisation diversity view' });
    expect(axes).toHaveLength(1);
    expect(chartSrc('Role-holders by organisation')).toContain('affiliation_donut.png');
    expect(chartSrc('Single-employer repos by org')).toContain('single_employer_repos_by_org.png');

    await userEvent.click(within(axes[0]).getByRole('button', { name: 'Committers' }));

    expect(chartSrc('Role-holders by organisation')).toContain('affiliation_donut_committers.png');
    expect(chartSrc('Single-employer repos by org')).toContain(
      'single_employer_repos_by_org_committers.png',
    );
    // The chart with no role axis is untouched by the card's tabs.
    expect(chartSrc('Single-employer teams by org')).toContain('single_employer_teams_by_org.png');
  });

  it('leaves a chart with its own variant set on its own tabs', async () => {
    // The period-tabbed pipeline card shares no axis with anything, so its
    // tabs stay under the figure and keep their own state.
    await openGovernance();

    expect(
      screen.queryByRole('group', { name: 'Maintainer pipeline view' }),
    ).not.toBeInTheDocument();
    const own = screen.getByRole('group', { name: 'Unique active contributors by role view' });
    expect(within(own).getByRole('button', { name: 'By year' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('shows the active tab’s note and methodology in the lightbox', async () => {
    await openDiversity();
    const axis = screen.getByRole('group', { name: 'Organisation diversity view' });

    await userEvent.click(within(axis).getByRole('button', { name: 'Committers' }));
    await userEvent.click(screen.getByAltText('Role-holders by organisation'));

    // The committer tab must describe committers — it used to show the
    // maintainer note, which misdescribed its own population.
    const lightbox = await screen.findByRole('dialog');
    expect(within(lightbox).getByText('The committer bench by employer.')).toBeInTheDocument();
    expect(within(lightbox).getByText('Count committers.')).toBeInTheDocument();
    expect(
      within(lightbox).queryByText('The maintainer bench by employer.'),
    ).not.toBeInTheDocument();
  });

  it('downloads the active tab’s companion CSV', async () => {
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    vi.stubGlobal(
      'URL',
      Object.assign(Object.create(URL), {
        createObjectURL: () => 'blob:test',
        revokeObjectURL: () => {},
      }),
    );
    await openDiversity();
    const axis = screen.getByRole('group', { name: 'Organisation diversity view' });
    const card = screen.getByText('Organisation diversity').closest('section') as HTMLElement;

    await userEvent.click(within(axis).getByRole('button', { name: 'Committers' }));
    await userEvent.click(within(card).getByRole('button', { name: 'Download CSV' }));

    await vi.waitFor(() =>
      expect(
        vi
          .mocked(fetch)
          .mock.calls.some(([url]) => String(url).endsWith('committer_affiliations.csv')),
      ).toBe(true),
    );
    expect(
      vi
        .mocked(fetch)
        .mock.calls.some(([url]) => String(url).endsWith('maintainer_affiliations.csv')),
    ).toBe(false);
  });
});

describe('Role-tabbed tables (#435)', () => {
  const openDiversity = async () => {
    render(<App />);
    await screen.findByRole('button', { name: 'Diversity' });
    await userEvent.click(screen.getByRole('button', { name: 'Diversity' }));
    return await screen.findByText('Organisation affiliations — reference');
  };

  it('renders one tabbed card instead of two stacked ones', async () => {
    await openDiversity();

    // The absorbed section is not a card of its own any more…
    expect(screen.queryByText('Committer affiliations — reference')).not.toBeInTheDocument();
    // …and its document is never fetched: its rows travel inside this card.
    expect(
      vi
        .mocked(fetch)
        .mock.calls.some(([url]) => String(url).endsWith('committeraffiliations.json')),
    ).toBe(false);

    const roles = screen.getByRole('group', { name: 'Role' });
    expect(within(roles).getByRole('button', { name: 'Maintainers' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByText('alice')).toBeInTheDocument();
    expect(screen.queryByText('dave')).not.toBeInTheDocument();
  });

  it('swaps rows, columns and the freshness stamp with the tab', async () => {
    await openDiversity();
    const roles = screen.getByRole('group', { name: 'Role' });
    const table = screen.getByRole('table');

    expect(within(table).getByText('maintainer')).toBeInTheDocument();

    await userEvent.click(within(roles).getByRole('button', { name: 'Committers' }));

    // The count column is named for the role it counts, so the tabs differ in
    // shape and not only in their rows.
    expect(within(screen.getByRole('table')).getByText('committer')).toBeInTheDocument();
    expect(within(screen.getByRole('table')).queryByText('maintainer')).not.toBeInTheDocument();
    expect(screen.getByText('dave')).toBeInTheDocument();
    expect(screen.queryByText('alice')).not.toBeInTheDocument();
    expect(screen.getByText(/data as of 2026-07-26 10:00/)).toBeInTheDocument();
    expect(screen.getByText(/whose highest role anywhere is committer/)).toBeInTheDocument();
  });

  it('keeps period tabs and role tabs distinguishable', async () => {
    // Role tabs are not PeriodTabs: they carry no "All time" null state, and
    // the two axes have to stay tellable apart on a table that has both.
    await openDiversity();

    expect(within(screen.getByRole('group', { name: 'Role' })).getAllByRole('button')).toHaveLength(
      2,
    );
    expect(screen.queryByRole('group', { name: 'Time range' })).not.toBeInTheDocument();
  });

  it('resolves a deep link to an absorbed section, with its tab active', async () => {
    // `#widget=committeraffiliations` predates the merge and must still land:
    // on the card that absorbed it, scrolled to and with that tab active.
    const scrolled: Element[] = [];
    vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(function (this: Element) {
      scrolled.push(this);
    });
    window.location.hash = 'tab=Diversity&widget=committeraffiliations';
    render(<App />);

    const card = await screen.findByText('Organisation affiliations — reference');
    expect(card).toBeInTheDocument();
    await screen.findByText('dave');
    await vi.waitFor(() => expect(scrolled.map((el) => el.id)).toContain('affiliations'));
    expect(
      within(screen.getByRole('group', { name: 'Role' })).getByRole('button', {
        name: 'Committers',
      }),
    ).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByText('alice')).not.toBeInTheDocument();
  });
});

describe('Per-tab explainers', () => {
  it("each tab shows its own explainer and no other tab's", async () => {
    render(<App />);
    await screen.findByRole('button', { name: 'Governance' });

    await userEvent.click(screen.getByRole('button', { name: 'Governance' }));
    await screen.findByText('Role holders');
    expect(screen.getByText('How to read this — what each column means')).toBeInTheDocument();
    expect(
      screen.queryByText('How to read this tab — what the numbers mean'),
    ).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'HIPs' }));
    await screen.findByText('Implementation coverage matrix');
    expect(screen.getByText('How to read this tab — what the numbers mean')).toBeInTheDocument();
    expect(screen.queryByText('How to read this — what each column means')).not.toBeInTheDocument();
  });
});

describe('Cell formats', () => {
  it('renders a presence column as a labelled chip, not a bare tick', async () => {
    const { FormattedCell } = await import('../components/FormattedCell');
    const { container } = render(
      <>
        <FormattedCell value={true} format="presence" />
        <FormattedCell value={false} format="presence" />
      </>,
    );

    expect(container.textContent).toBe('presentmissing');
    expect(container.querySelector('.chip-merged')).toBeInTheDocument();
    expect(container.querySelector('.chip-none')).toBeInTheDocument();
  });
});

describe('KPI tiles', () => {
  it('expands an annotated tile into its note and derivation steps', async () => {
    render(<App />);
    await userEvent.click(await screen.findByRole('button', { name: 'Governance' }));
    await screen.findByText('Role holders');

    // A tile with an annotation is a button; one without stays inert.
    const tile = screen.getByRole('button', { name: /maintainers 103/ });
    await userEvent.click(tile);

    const dialog = await screen.findByRole('dialog');
    expect(
      within(dialog).getByText('People whose highest role anywhere is maintainer.'),
    ).toBeInTheDocument();
    expect(within(dialog).getByText('Step-by-step methodology')).toBeInTheDocument();
    expect(within(dialog).getAllByRole('listitem')).toHaveLength(3);

    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /quiet teams 2/ })).not.toBeInTheDocument();
  });
});

describe('Resilience', () => {
  it('renders what loaded and names what did not, instead of blanking the tab', async () => {
    // The tab's only table 404s; its charts and tiles must survive it.
    vi.unstubAllGlobals();
    const { MANIFEST } = await import('./fixtures');
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).endsWith('manifest.json')) return new Response(JSON.stringify(MANIFEST));
        if (String(url).endsWith('roles.json')) return new Response('gone', { status: 404 });
        return new Response('{}', { status: 200 });
      }),
    );

    render(<App />);
    await userEvent.click(await screen.findByRole('button', { name: 'Governance' }));

    // The failure is named rather than silent or fatal…
    expect(await screen.findByText(/Could not load/)).toBeInTheDocument();
    expect(screen.getByText(/Role holders/)).toBeInTheDocument();
    // …while the rest of the tab still renders.
    expect(screen.getByText('Maintainer pipeline')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /maintainers 103/ })).toBeInTheDocument();
  });
});

describe('Section groups', () => {
  it('gives colliding group names distinct keys and anchors', async () => {
    const { SectionGroups } = await import('../components/SectionGroups');
    // Distinct names that slug identically, plus an outright repeat.
    const { container } = render(
      <SectionGroups
        groups={[
          ['Roles & teams', <p key="a">a</p>],
          ['Roles  teams', <p key="b">b</p>],
          ['Roles & teams', <p key="c">c</p>],
        ]}
      />,
    );

    const ids = [...container.querySelectorAll('details.group')].map((el) => el.id);
    expect(new Set(ids).size).toBe(3); // no duplicate DOM ids

    // Every jump button scrolls its own group, even under name collisions.
    const scrolled: Element[] = [];
    const spy = vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(function (
      this: Element,
    ) {
      scrolled.push(this);
    });
    for (const button of container.querySelectorAll('button.jbtn')) {
      await userEvent.click(button);
    }
    spy.mockRestore();
    expect(scrolled.map((el) => el.id)).toEqual(ids);
  });

  it('jumping to a group keeps the active tab and the hash state (#342)', async () => {
    await openGovernance();
    expect(window.location.hash).toContain('tab=Governance');

    await userEvent.click(screen.getByRole('button', { name: 'Roles & teams' }));

    // The jump must not clobber the hash the app stores its state in: the
    // Governance content is still on screen and the hash still names the tab.
    expect(screen.getByText('Role holders')).toBeInTheDocument();
    expect(window.location.hash).toContain('tab=Governance');
    expect(window.location.hash).not.toContain('grp-');
  });
});

describe('Loading, empty-filter, and error states (#343)', () => {
  it('shows the header and an initial-load placeholder before the manifest arrives', async () => {
    vi.unstubAllGlobals();
    let resolveManifest!: (response: Response) => void;
    const pending = new Promise<Response>((resolve) => {
      resolveManifest = resolve;
    });
    const { MANIFEST } = await import('./fixtures');
    stubApi({ 'manifest.json': () => pending });

    render(<App />);

    expect(
      screen.getByRole('heading', { name: 'Hiero — analytics dashboard' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('status', { name: 'Loading dashboard' })).toBeInTheDocument();

    resolveManifest(new Response(JSON.stringify(MANIFEST)));
    expect(await screen.findByRole('button', { name: 'Governance' })).toBeInTheDocument();
    expect(screen.queryByRole('status', { name: 'Loading dashboard' })).not.toBeInTheDocument();
  });

  it('shows a tab-switch skeleton while a section is still fetching', async () => {
    vi.unstubAllGlobals();
    let resolveRoles!: (response: Response) => void;
    const pendingRoles = new Promise<Response>((resolve) => {
      resolveRoles = resolve;
    });
    const { GOV_DOC } = await import('./fixtures');
    stubApi({ 'roles.json': () => pendingRoles });

    render(<App />);
    await userEvent.click(await screen.findByRole('button', { name: 'Governance' }));

    expect(screen.getByRole('status', { name: 'Loading tab' })).toBeInTheDocument();
    expect(screen.queryByText('Role holders')).not.toBeInTheDocument();

    resolveRoles(new Response(JSON.stringify(GOV_DOC)));
    expect(await screen.findByText('Role holders')).toBeInTheDocument();
    expect(screen.queryByRole('status', { name: 'Loading tab' })).not.toBeInTheDocument();
  });

  it('shows a no-matches message when a filter excludes every row, and clears it', async () => {
    await openGovernance();

    await userEvent.type(screen.getByPlaceholderText('Filter…'), 'nobody-has-this-name');
    expect(await screen.findByText(/No rows match/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'clear the filter?' })).toBeInTheDocument();
    expect(screen.queryByText('alice')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'clear the filter?' }));
    expect(await screen.findByText('alice')).toBeInTheDocument();
    expect(screen.queryByText(/No rows match/)).not.toBeInTheDocument();
  });

  it('shows a fatal error with a retry button when the manifest fails to load', async () => {
    vi.unstubAllGlobals();
    const { MANIFEST } = await import('./fixtures');
    let attempt = 0;
    stubApi({
      'manifest.json': () => {
        attempt += 1;
        return attempt === 1
          ? new Response('nope', { status: 500 })
          : new Response(JSON.stringify(MANIFEST));
      },
    });

    render(<App />);

    expect(
      screen.getByRole('heading', { name: 'Hiero — analytics dashboard' }),
    ).toBeInTheDocument();
    expect(await screen.findByText(/Failed to load the dashboard data/)).toBeInTheDocument();
    expect(screen.getByText('Error details')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('button', { name: 'Governance' })).toBeInTheDocument();
    expect(screen.queryByText(/Failed to load the dashboard data/)).not.toBeInTheDocument();
  });
});
