/**
 * The theme plumbing: the stored choice round-trips, "system" means no
 * data-theme attribute, unavailable storage degrades to "system" instead of
 * throwing, and the pre-paint script in public/ agrees with src/theme.ts.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { THEME_STORAGE_KEY, applyTheme, readTheme } from '../theme';
// The real file, as text — the test runs exactly what browsers run.
import script from '../../public/theme-init.js?raw';

const root = document.documentElement;

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
  root.removeAttribute('data-theme');
});

describe('theme', () => {
  it('defaults to following the OS', () => {
    expect(readTheme()).toBe('system');
    expect(root).not.toHaveAttribute('data-theme');
  });

  it('applies and remembers an explicit choice', () => {
    applyTheme('dark');
    expect(root).toHaveAttribute('data-theme', 'dark');
    expect(readTheme()).toBe('dark');

    applyTheme('light');
    expect(root).toHaveAttribute('data-theme', 'light');
    expect(readTheme()).toBe('light');
  });

  it('returning to system clears both the attribute and the stored choice', () => {
    applyTheme('dark');
    applyTheme('system');
    expect(root).not.toHaveAttribute('data-theme');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
  });

  it('ignores a stored value it does not recognise', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'sepia');
    expect(readTheme()).toBe('system');
  });

  it('still applies the theme when storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });

    expect(readTheme()).toBe('system');
    expect(() => applyTheme('dark')).not.toThrow();
    expect(root).toHaveAttribute('data-theme', 'dark');
  });

  it('the pre-paint script applies what theme.ts stored', () => {
    // public/theme-init.js cannot import theme.ts (it runs before the bundle),
    // so this is what keeps the two agreeing on the key and the values.
    const run = () => new Function(script)();

    applyTheme('dark');
    root.removeAttribute('data-theme'); // a fresh page load
    run();
    expect(root).toHaveAttribute('data-theme', 'dark');

    applyTheme('system');
    run();
    expect(root).not.toHaveAttribute('data-theme');
  });
});
