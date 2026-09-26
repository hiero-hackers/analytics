/**
 * One table cell rendered per the API's column format — the single place the
 * display formats (hip, date, link, evidence, status, flag, presence, number)
 * live. The HIP views add their formats here rather than growing their own
 * switches.
 */

import { Badge } from '@/components/ui/badge';
import type { ColumnFormat } from '../api';
import { dateStamp } from '../format';
import { safeUrl } from '../safety';

// Fixed locale: the dashboard's prose is en, and a deterministic separator
// keeps snapshots and tests stable across viewer locales.
const NUMBER_FORMAT = new Intl.NumberFormat('en-US');

type Tone = 'ok' | 'warn' | 'neg' | 'info' | 'neutral';

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
      return <span className="font-semibold whitespace-nowrap tabular-nums">HIP-{text}</span>;
    case 'date':
      // UTC-converted date, full raw timestamp on hover. Conversion, not
      // truncation: slicing an offset-bearing value can misreport the day.
      return <span title={text}>{dateStamp(text)}</span>;
    case 'link': {
      // The href comes from generated data; an unsafe scheme renders as inert
      // text rather than a clickable link.
      const href = safeUrl(text);
      return href ? (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-link underline-offset-4 hover:underline"
        >
          open ↗
        </a>
      ) : (
        <>{text}</>
      );
    }
    case 'evidence': {
      const tone = text === 'merged' ? 'ok' : text === 'open_only' ? 'warn' : 'neutral';
      return <Badge variant={tone}>{text.replace('_', ' ')}</Badge>;
    }
    case 'status':
      return <Badge variant="info">{text}</Badge>;
    case 'staleness': {
      // Matches analysis/releases.py's staleness_bucket values exactly.
      const tone: Record<string, Tone> = {
        never_released: 'neutral',
        overdue: 'neg',
        watch: 'warn',
        on_pace: 'ok',
        insufficient_history: 'neutral',
      };
      const label: Record<string, string> = {
        never_released: 'never released',
        overdue: 'overdue',
        watch: 'watch',
        on_pace: 'on pace',
        insufficient_history: 'not enough history',
      };
      return <Badge variant={tone[text] ?? 'neutral'}>{label[text] ?? text}</Badge>;
    }
    case 'flag':
      return <>{text === 'true' || text === 'True' ? '✓' : '—'}</>;
    case 'presence': {
      // A yes/no column: a labelled chip reads at a glance where a bare tick
      // leaves the reader decoding an empty-looking cell.
      const present = text === 'true' || text === 'True';
      return <Badge variant={present ? 'ok' : 'neutral'}>{present ? 'present' : 'missing'}</Badge>;
    }
    default:
      return <>{text}</>;
  }
}
