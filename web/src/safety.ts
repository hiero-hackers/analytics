/**
 * Guards for values that originate outside this repository.
 *
 * Most cells on the dashboard are mechanically derived from public GitHub
 * activity, and some of that is attacker-controlled free text: anyone can open
 * a PR in a public repo and choose its title or branch name. React escapes it
 * safely when rendering, but two sinks leave React's protection behind — a
 * spreadsheet opening a downloaded CSV, and the browser following a link — so
 * both are neutralised here rather than at each call site.
 */

/** URL schemes a data-driven link may use. */
const SAFE_URL_SCHEMES = new Set(['http:', 'https:', 'mailto:']);

/**
 * The URL if it is safe to link to, otherwise null.
 *
 * Blocks `javascript:` and `data:` hrefs, which would otherwise execute in the
 * page's origin when a reader clicks a table cell. Relative URLs resolve
 * against the page and are allowed.
 */
export function safeUrl(value: string): string | null {
  const text = value.trim();
  if (!text) {
    return null;
  }
  try {
    return SAFE_URL_SCHEMES.has(new URL(text, window.location.href).protocol) ? text : null;
  } catch {
    return null;
  }
}

// Cells beginning with one of these can execute as a formula when the CSV is
// opened in Excel or Google Sheets (CSV injection) — the same list the Python
// side neutralises for its spreadsheet copies (export/csv_safety.py). The
// control characters count because a leading tab, CR or LF is stripped on
// import, exposing whatever follows it to the formula parser.
const FORMULA_PREFIXES = ['=', '+', '-', '@', '\t', '\r', '\n'];

/**
 * A cell a spreadsheet will treat as text, never as a formula.
 *
 * Prefixes a formula-triggering value with an apostrophe. A lone "-" is left
 * alone: it is the dashboard's empty-cell placeholder, not a formula.
 */
export function csvSafe(value: unknown): string {
  const text = value === null || value === undefined ? '' : String(value);
  return text && text !== '-' && FORMULA_PREFIXES.includes(text[0]) ? `'${text}` : text;
}
