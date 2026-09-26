/*
 * Applies a stored explicit theme before first paint, so a reader who chose
 * light or dark never sees a flash of the OS theme. Loaded as an external
 * file because the CSP forbids inline scripts (script-src 'self').
 *
 * Mirrors src/theme.ts: same storage key, same values. No stored choice (or
 * "system", or unreadable storage) leaves <html> without data-theme, which
 * means "follow the OS" to the stylesheet.
 */
(function () {
  try {
    var choice = window.localStorage.getItem('hiero-analytics-theme');
    if (choice === 'light' || choice === 'dark') {
      document.documentElement.setAttribute('data-theme', choice);
    }
  } catch {
    // Storage blocked (privacy mode, sandboxed frame): follow the OS.
  }
})();
