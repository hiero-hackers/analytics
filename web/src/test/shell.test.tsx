/**
 * The app shell: the header's theme menu, the sidebar's tabs and "On this
 * page" contents, and the phone layout (tabs in a Sheet, groups in a strip).
 */

import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { THEME_STORAGE_KEY } from '../theme';
import { MANIFEST, stubApi } from './fixtures';

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

    // HIPs is no longer a top-level tab; it appears as Governance's member.
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
      screen.getAllByText(name).find((el) => el.tagName === 'SUMMARY')!.parentElement!;
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
