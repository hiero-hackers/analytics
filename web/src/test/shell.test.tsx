import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { THEME_STORAGE_KEY } from '../theme';
import { MANIFEST } from './fixtures';
import { stubApi } from './stubApi';

beforeEach(() => {
  vi.unstubAllGlobals();
  stubApi();
});

afterEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
});

const openGovernance = async () => {
  render(<App />);
  await userEvent.click(await screen.findByRole('button', { name: 'Governance' }));
  await screen.findByText('Role holders');
};

describe('Theme menu', () => {
  const theme = () => screen.getByRole('radiogroup', { name: 'Theme' });

  it('forces a theme, remembers it, and returns to following the OS', async () => {
    render(<App />);
    expect(within(theme()).getByRole('radio', { name: 'System' })).toBeChecked();

    await userEvent.click(within(theme()).getByRole('radio', { name: 'Dark' }));
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    expect(within(theme()).getByRole('radio', { name: 'Dark' })).toBeChecked();

    await userEvent.click(within(theme()).getByRole('radio', { name: 'System' }));
    expect(document.documentElement).not.toHaveAttribute('data-theme');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
  });

  it('keeps a choice when the active option is clicked again', async () => {
    render(<App />);
    await userEvent.click(within(theme()).getByRole('radio', { name: 'Light' }));
    await userEvent.click(within(theme()).getByRole('radio', { name: 'Light' }));
    expect(document.documentElement).toHaveAttribute('data-theme', 'light');
    expect(within(theme()).getByRole('radio', { name: 'Light' })).toBeChecked();
  });

  it('opens on the stored choice', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light');
    render(<App />);
    expect(within(theme()).getByRole('radio', { name: 'Light' })).toBeChecked();
  });
});

describe('Sidebar tabs', () => {
  it('marks the active tab as the current page', async () => {
    await openGovernance();
    const nav = screen.getByRole('navigation', { name: 'Dashboard' });
    expect(within(nav).getByRole('button', { name: 'Governance' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(within(nav).getByRole('button', { name: 'HIPs' })).not.toHaveAttribute('aria-current');
  });

  it('marks the tabs the selected organisation has no data for', async () => {
    window.location.hash = 'org=hiero-hackers';
    render(<App />);
    const nav = await screen.findByRole('navigation', { name: 'Dashboard' });
    // hiero-hackers has contributor tables only.
    const governance = await within(nav).findByRole('button', { name: 'Governance' });
    expect(governance).toHaveAttribute('aria-description', 'No data for hiero-hackers');
    expect(within(nav).getByRole('button', { name: 'Contributors' })).not.toHaveAttribute(
      'aria-description',
    );
  });

  it('writes the hash even when the active tab is clicked again', async () => {
    // A shared link can carry a widget and org the reader then clears by hand;
    // clicking the tab they are on must still put `tab=` back in the URL.
    await openGovernance();
    window.location.hash = '';
    await userEvent.click(screen.getByRole('button', { name: 'Governance' }));
    expect(window.location.hash).toContain('tab=Governance');
  });

  it("nests an umbrella tab's members under it", async () => {
    vi.unstubAllGlobals();
    stubApi({
      'manifest.json': () =>
        new Response(JSON.stringify({ ...MANIFEST, macro_parents: { HIPs: 'Governance' } })),
    });
    await openGovernance();
    const nav = screen.getByRole('navigation', { name: 'Dashboard' });

    // HIPs is a member of Governance, not a top-level tab.
    const member = within(nav).getByRole('button', { name: 'HIPs' });
    expect(member.closest('[data-sidebar="menu-sub"]')).not.toBeNull();

    await userEvent.click(member);
    expect(await screen.findByText('Implementation coverage matrix')).toBeInTheDocument();
    expect(member).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('button', { name: 'Governance' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });
});

describe('On this page', () => {
  it("lists the tab's groups and highlights the one scrolled to", async () => {
    // jsdom has no IntersectionObserver: capture the callback and drive it,
    // with group positions stubbed as a scroll would leave them.
    let notify: () => void = () => {};
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        constructor(callback: () => void) {
          notify = callback;
        }
        observe() {}
        disconnect() {}
      },
    );
    await openGovernance();
    const nav = screen.getByRole('navigation', { name: 'Dashboard' });
    const roles = within(nav).getByRole('button', { name: 'Roles & teams' });
    expect(roles).not.toHaveAttribute('aria-current');

    // The Roles group's top has scrolled up past the header; later ones haven't.
    const top = (name: string) =>
      document.querySelector<HTMLElement>(`[id^="grp-"][id$="${name.replace(/\W+/g, '-')}"]`)!;
    for (const [name, y] of [
      ['Pipeline charts', -800],
      ['Roles & teams', 120],
    ] as const) {
      vi.spyOn(top(name), 'getBoundingClientRect').mockReturnValue({ top: y } as DOMRect);
    }
    act(() => notify());

    expect(roles).toHaveAttribute('aria-current', 'location');
    expect(within(nav).getByRole('button', { name: 'Pipeline charts' })).not.toHaveAttribute(
      'aria-current',
    );
  });
});

describe('Phone layout', () => {
  beforeEach(() => {
    window.innerWidth = 390;
  });

  it('keeps the tabs in a Sheet that opens from the header and closes on choosing', async () => {
    render(<App />);
    await screen.findByRole('combobox', { name: 'Organisation' });
    // No inline sidebar on a phone: the tabs are behind the header button.
    expect(screen.queryByRole('button', { name: 'Governance' })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Open sections' }));
    const sheet = await screen.findByRole('dialog', { name: 'Sections' });
    await userEvent.click(within(sheet).getByRole('button', { name: 'Governance' }));

    expect(screen.queryByRole('dialog', { name: 'Sections' })).not.toBeInTheDocument();
    expect(await screen.findByText('Role holders')).toBeInTheDocument();
    expect(window.location.hash).toContain('tab=Governance');
  });

  it('closes the Sheet on Escape and returns focus to the header button', async () => {
    render(<App />);
    await screen.findByRole('combobox', { name: 'Organisation' });
    const trigger = screen.getByRole('button', { name: 'Open sections' });

    await userEvent.click(trigger);
    await screen.findByRole('dialog', { name: 'Sections' });
    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('dialog', { name: 'Sections' })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('moves the theme switch from the header into the Sheet', async () => {
    render(<App />);
    await screen.findByRole('combobox', { name: 'Organisation' });
    expect(screen.queryByRole('radiogroup', { name: 'Theme' })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Open sections' }));
    const sheet = await screen.findByRole('dialog', { name: 'Sections' });
    expect(within(sheet).getByRole('radiogroup', { name: 'Theme' })).toBeInTheDocument();
  });

  it('shows the groups as a strip and the freshness under the tab title', async () => {
    window.location.hash = 'tab=Governance';
    render(<App />);
    await screen.findByText('Role holders');

    const strip = await screen.findByRole('navigation', { name: 'Jump to' });
    expect(within(strip).getByRole('button', { name: 'Roles & teams' })).toBeInTheDocument();
    expect(screen.getByText('2026-07-25 21:00 UTC').closest('p')).toHaveTextContent(
      'Data as of 2026-07-25 21:00 UTC',
    );
  });
});

describe('Navigation search', () => {
  it('finds a page with the keyboard shortcut and navigates with Enter', async () => {
    render(<App />);
    await screen.findByRole('button', { name: 'Governance' });
    await userEvent.keyboard('{Control>}k{/Control}');
    const dialog = screen.getByRole('dialog', { name: 'Explore the dashboard' });
    const input = within(dialog).getByRole('textbox', { name: 'Search pages and sections' });
    await userEvent.type(input, 'Governance{Enter}');
    expect(await screen.findByText('Role holders')).toBeInTheDocument();
    await waitFor(() => expect(window.location.hash).toContain('tab=Governance'));
    expect(screen.queryByRole('dialog', { name: 'Explore the dashboard' })).not.toBeInTheDocument();
  });

  it('handles no matches and returns focus when dismissed', async () => {
    render(<App />);
    const trigger = screen.getByRole('button', { name: 'Search dashboard' });
    await userEvent.click(trigger);
    await userEvent.type(
      screen.getByRole('textbox', { name: 'Search pages and sections' }),
      'zzzz',
    );
    expect(screen.getByRole('status')).toHaveTextContent('No sections match');
    await userEvent.keyboard('{Escape}');
    expect(trigger).toHaveFocus();
  });
});

describe('Header status', () => {
  it('states the data age in words and flags it past the daily refresh', async () => {
    const { FreshnessStatus } = await import('../components/AppHeader');
    const asOf = '2026-07-19T00:00:00Z';
    const at = (hours: number) => Date.parse(asOf) + hours * 3_600_000;
    const { rerender } = render(<FreshnessStatus dataAsOf={asOf} now={at(5)} />);
    expect(screen.getByText('Updated 5 hours ago')).toBeInTheDocument();
    rerender(<FreshnessStatus dataAsOf={asOf} now={at(30)} />);
    expect(screen.getByText('Updated 30 hours ago')).toBeInTheDocument();
    // 36 h mirrors the exporter's STALE_AFTER.
    rerender(<FreshnessStatus dataAsOf={asOf} now={at(37)} />);
    expect(screen.getByText('2 days old, refresh overdue')).toHaveClass('text-warn-ink');
    rerender(<FreshnessStatus dataAsOf={asOf} now={at(24 * 71)} />);
    expect(screen.getByText('71 days old, refresh overdue')).toHaveClass('text-warn-ink');
    expect(screen.getByText('2026-07-19 00:00 UTC').closest('p')).toHaveTextContent(
      'Data as of 2026-07-19 00:00 UTC',
    );
  });

  it('shows each organisation’s GitHub avatar, falling back to its own initial', async () => {
    const { OrgAvatar } = await import('../components/OrgSwitcher');
    const { container } = render(
      <>
        <OrgAvatar org="hiero-ledger" />
        <OrgAvatar org="hiero-hackers" />
      </>,
    );
    const avatars = [...container.querySelectorAll('img')];
    // github.com/<org>.png resolves to the organisation's real avatar by id.
    expect(avatars.map((img) => img.getAttribute('src'))).toEqual([
      'https://github.com/hiero-ledger.png?size=64',
      'https://github.com/hiero-hackers.png?size=64',
    ]);
    avatars.forEach((img) => fireEvent.error(img));
    expect(container.querySelectorAll('img')).toHaveLength(0);
    expect([...container.querySelectorAll('span')].map((mark) => mark.textContent)).toEqual([
      'L',
      'H',
    ]);
  });
});

describe('Organisation names and brands from the manifest', () => {
  /** The fixture manifest, with hiero-hackers given a display name and a brand key. */
  const branded = (brand: string) => ({
    ...MANIFEST,
    orgs: {
      ...MANIFEST.orgs,
      'hiero-hackers': { ...MANIFEST.orgs['hiero-hackers'], display_name: 'Hiero Hackers', brand },
    },
  });

  const serve = (manifest: unknown) =>
    stubApi({ 'manifest.json': () => new Response(JSON.stringify(manifest)) });

  const bannerLogos = () =>
    [...screen.getByRole('banner').querySelectorAll('img')]
      .map((img) => img.getAttribute('src'))
      .filter((src) => src?.includes('brand/'));

  it('labels each organisation by its display name, keeping the login as the value', async () => {
    serve(branded('hackers'));
    render(<App />);

    const option = await screen.findByRole('option', { name: 'Hiero Hackers' });
    expect(option).toHaveValue('hiero-hackers');
    // An org without a display name is labelled by its login, as before.
    expect(screen.getByRole('option', { name: 'hiero-ledger' })).toBeInTheDocument();
  });

  it('shows the selected organisation’s logo and returns to Hiero when switching back', async () => {
    window.location.hash = 'org=hiero-hackers';
    serve(branded('hackers'));
    render(<App />);

    expect(
      await within(screen.getByRole('banner')).findByText('Hiero Hackers analytics'),
    ).toBeInTheDocument();
    expect(bannerLogos()).toEqual(['/brand/hackers/logo.svg', '/brand/hackers/logo-dark.svg']);

    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: 'Organisation' }),
      'hiero-ledger',
    );
    expect(within(screen.getByRole('banner')).getByText('Hiero analytics')).toBeInTheDocument();
    expect(bannerLogos()).toEqual(['/brand/hiero-logo.svg', '/brand/hiero-logo-dark.svg']);
  });

  it('falls back to the Hiero mark when an organisation’s logo fails to load', async () => {
    window.location.hash = 'org=hiero-hackers';
    serve(branded('hackers'));
    render(<App />);
    await within(screen.getByRole('banner')).findByText('Hiero Hackers analytics');

    fireEvent.error(
      screen.getByRole('banner').querySelector('img[src="/brand/hackers/logo.svg"]')!,
    );

    expect(within(screen.getByRole('banner')).getByText('Hiero analytics')).toBeInTheDocument();
    expect(bannerLogos()).toEqual(['/brand/hiero-logo.svg', '/brand/hiero-logo-dark.svg']);
  });

  it('ignores a brand key that is not a plain slug', async () => {
    const { brandLogo } = await import('../brand');

    expect(brandLogo('../../evil', '/')).toBeNull();
    expect(brandLogo('Hackers', '/')).toBeNull();
    expect(brandLogo('hiero', '/')).toBeNull();
    expect(brandLogo(undefined, '/')).toBeNull();
    expect(brandLogo('lfdt-clpr', '/base/')).toEqual({
      light: '/base/brand/lfdt-clpr/logo.svg',
      dark: '/base/brand/lfdt-clpr/logo-dark.svg',
    });
  });
});
