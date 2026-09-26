/**
 * The reader's theme choice: follow the OS ("system", the default) or force
 * light/dark. A forced choice is `data-theme` on <html>, which the stylesheet's
 * palette and `dark` variant key on; "system" is the attribute's absence.
 *
 * The choice persists in localStorage. public/theme-init.js applies it before
 * first paint and must agree with this file on the key and values. Storage can
 * be unavailable (privacy modes, sandboxed frames), so every access is guarded
 * and failure means "system", never a crash.
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

/** Apply `choice` to <html> and remember it for the next visit. */
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
