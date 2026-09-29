/**
 * Paper for printing one chart (`ChartPrintDialog`): sizes, the page rule, the
 * orientation a chart fits best, and the reader's remembered paper size. All
 * lengths are millimetres; CSS pixels are 1/96 in on paper as on screen.
 */

export type Paper = 'a4' | 'letter';
export type Orientation = 'portrait' | 'landscape';

export const PAPERS: Record<Paper, { label: string; size: string; width: number; height: number }> =
  {
    a4: { label: 'A4', size: 'A4', width: 210, height: 297 },
    letter: { label: 'Letter', size: 'letter', width: 215.9, height: 279.4 },
  };

/** The page margin on every side. */
export const MARGIN = 12;
export const PX_PER_MM = 96 / 25.4;
/** Kept off the printable height, so rounding can never spill a blank second page. */
const SAFETY = 1;
/** The title, filters, legend and notes around the chart, when comparing orientations. */
const CHROME = 60;

export function paperBox(paper: Paper, orientation: Orientation) {
  const { width, height } = PAPERS[paper];
  return orientation === 'portrait' ? { width, height } : { width: height, height: width };
}

/** The printable area inside the margins. */
export function contentBox(paper: Paper, orientation: Orientation) {
  const { width, height } = paperBox(paper, orientation);
  return { width: width - 2 * MARGIN, height: height - 2 * MARGIN - SAFETY };
}

/**
 * The orientation that draws a chart of this shape (width ÷ height) largest:
 * the one giving it the most height once it is also narrow enough to fit.
 */
export function bestOrientation(aspect: number, paper: Paper): Orientation {
  const fit = (orientation: Orientation) => {
    const { width, height } = contentBox(paper, orientation);
    return Math.min(width / aspect, height - CHROME);
  };
  return fit('portrait') > fit('landscape') ? 'portrait' : 'landscape';
}

/**
 * The page rule the browser prints with. The page itself has no margin, so the
 * browser has no room for its own header and footer (date, title, URL); the
 * sheet pads itself by `MARGIN` on every printed page instead (print.css).
 */
export function pageRule(paper: Paper, orientation: Orientation) {
  return `@page { size: ${PAPERS[paper].size} ${orientation}; margin: 0; @bottom-left { content: none; } @bottom-right { content: none; } }`;
}

/** Regions whose default office paper is Letter; everywhere else prints on A4. */
const LETTER_REGIONS = new Set(['US', 'CA', 'MX', 'PH', 'CL', 'CO', 'VE', 'GT', 'CR', 'PA', 'PR']);

export function defaultPaper(language = globalThis.navigator?.language ?? 'en'): Paper {
  try {
    const region = new Intl.Locale(language).maximize().region;
    return region && LETTER_REGIONS.has(region) ? 'letter' : 'a4';
  } catch {
    return 'a4';
  }
}

export const PAPER_STORAGE_KEY = 'hiero-analytics-print-paper';

/** The paper size the reader last printed on, or their region's default. */
export function storedPaper(): Paper {
  try {
    const stored = window.localStorage.getItem(PAPER_STORAGE_KEY);
    if (stored === 'a4' || stored === 'letter') return stored;
  } catch {
    // Storage can be blocked; the regional default still applies.
  }
  return defaultPaper();
}

export function storePaper(paper: Paper) {
  try {
    window.localStorage.setItem(PAPER_STORAGE_KEY, paper);
  } catch {
    // Not remembered, but printing is unaffected.
  }
}

/**
 * A control's accessible name as a printed filter label: "Role activity chart
 * style" on a chart titled "Role activity" prints as "Chart style".
 */
export function filterLabel(ariaLabel: string, title: string) {
  const rest = ariaLabel.startsWith(title)
    ? ariaLabel.slice(title.length).replace(/^[\s:·—-]+/, '')
    : ariaLabel;
  return rest ? `${rest[0].toUpperCase()}${rest.slice(1)}` : ariaLabel;
}
