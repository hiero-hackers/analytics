/**
 * The theme choice: a forced light/dark is `data-theme` on <html>, "system" its
 * absence. public/theme-init.js applies it before first paint and must agree on
 * the storage key and values. Storage failures fall back to "system".
 */

export type ThemeChoice = 'system' | 'light' | 'dark';

export const THEME_STORAGE_KEY = 'hiero-analytics-theme';

/** The stored choice, or "system" when there is none or storage is unreadable. */
export function readTheme(): ThemeChoice {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return stored === 'light' || stored === 'dark' ? stored : 'system';
  } catch {
    return 'system';
  }
}

export function applyTheme(choice: ThemeChoice): void {
  const root = document.documentElement;
  if (choice === 'system') {
    root.removeAttribute('data-theme');
  } else {
    root.setAttribute('data-theme', choice);
  }
  try {
    if (choice === 'system') {
      window.localStorage.removeItem(THEME_STORAGE_KEY);
    } else {
      window.localStorage.setItem(THEME_STORAGE_KEY, choice);
    }
  } catch {
    // Not persisted, but still applied for this visit.
  }
}
