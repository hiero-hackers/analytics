/**
 * One table cell rendered per the API's column format — the single place the
 * display formats (hip, date, link, evidence, status, flag, presence, number)
 * live. The HIP views add their formats here rather than growing their own
 * switches.
 */

import type { ColumnFormat } from '../api';
import { dateStamp } from '../format';
import { safeUrl } from '../safety';

// Fixed locale: the dashboard's prose is en, and a deterministic separator
// keeps snapshots and tests stable across viewer locales.
const NUMBER_FORMAT = new Intl.NumberFormat('en-US');

export function FormattedCell({ value, format }: { value: unknown; format?: ColumnFormat }) {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  const text = String(value);
  switch (format) {
    case 'number': {
      // Separators for legibility; a non-numeric value (older API, junk row)
      // degrades to plain text rather than NaN.
      const numeric = typeof value === 'number' ? value : Number(text);
      return <>{Number.isFinite(numeric) ? NUMBER_FORMAT.format(numeric) : text}</>;
    }
    case 'hip':
      return <span className="cell-hip">HIP-{text}</span>;
    case 'date':
      // UTC-converted date, full raw timestamp on hover. Conversion, not
      // truncation: slicing an offset-bearing value can misreport the day.
      return <span title={text}>{dateStamp(text)}</span>;
    case 'link': {
      // The href comes from generated data; an unsafe scheme renders as inert
      // text rather than a clickable link.
      const href = safeUrl(text);
      return href ? (
        <a href={href} target="_blank" rel="noopener noreferrer" className="cell-link">
          open ↗
        </a>
      ) : (
        <>{text}</>
      );
    }
    case 'evidence': {
      const tone =
        text === 'merged' ? 'chip-merged' : text === 'open_only' ? 'chip-open' : 'chip-none';
      return <span className={`chip ${tone}`}>{text.replace('_', ' ')}</span>;
    }
    case 'status':
      return <span className="chip chip-spec">{text}</span>;
    case 'staleness': {
      // Matches analysis/releases.py's staleness_bucket values exactly.
      const tone: Record<string, string> = {
        never_released: 'chip-never',
        overdue: 'chip-overdue',
        watch: 'chip-watch',
        on_pace: 'chip-merged',
        insufficient_history: 'chip-none',
      };
      const label: Record<string, string> = {
        never_released: 'never released',
        overdue: 'overdue',
        watch: 'watch',
        on_pace: 'on pace',
        insufficient_history: 'not enough history',
      };
      return <span className={`chip ${tone[text] ?? 'chip-none'}`}>{label[text] ?? text}</span>;
    }
    case 'flag':
      return <>{text === 'true' || text === 'True' ? '✓' : '—'}</>;
    case 'presence': {
      // A yes/no column: a labelled chip reads at a glance where a bare tick
      // leaves the reader decoding an empty-looking cell.
      const present = text === 'true' || text === 'True';
      return (
        <span className={present ? 'chip chip-merged' : 'chip chip-none'}>
          {present ? 'present' : 'missing'}
        </span>
      );
    }
    default:
      return <>{text}</>;
  }
}
