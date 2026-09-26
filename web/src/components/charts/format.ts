/** Number, date and label formatting shared by the interactive chart views. */

import type { ChartDocument, ChartWindow, MatrixDocument, TimeseriesDocument } from '../../api';
import { stamp } from '../../format';

export const integer = new Intl.NumberFormat('en-US');
export const decimal = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });
export const percent = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 });

export function plural(label: string) {
  const word = label.toLowerCase();
  return word.endsWith('y') ? `${word.slice(0, -1)}ies` : `${word}s`;
}

export function shorten(name: string, length = 24) {
  return name.length > length ? `${name.slice(0, length - 1)}…` : name;
}

export function formatBucket(bucket: string, frequency: TimeseriesDocument['frequency']) {
  if (frequency === 'year' || frequency === 'week') return bucket;
  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'UTC',
    month: 'short',
    ...(frequency === 'month' ? { year: '2-digit' as const } : { day: 'numeric' as const }),
  }).format(new Date(`${bucket}${frequency === 'month' ? '-01' : ''}T00:00:00Z`));
}

/** The sentence under every chart saying which span of time it covers. */
export function windowText(
  window: ChartDocument['window'],
  anyPartial = false,
  subject = 'activity',
) {
  if ('first' in window) {
    return `Window: ${window.first ?? '—'} – ${window.last ?? '—'}.${anyPartial ? ' The final bucket may be incomplete.' : ''}`;
  }
  const { kind, days, end } = window as ChartWindow;
  const until = end ? `${stamp(end)} UTC` : null;
  if (kind === 'trailing')
    return `Window: the ${days} days before ${until ?? 'the source was generated'}.`;
  if (kind === 'all') return `Window: all recorded ${subject}${until ? `, as of ${until}` : ''}.`;
  return until ? `Snapshot as of ${until}.` : 'Snapshot; its date is unavailable.';
}

/** The shade for a value: 0 = none, 1..steps on the linear scale, null = missing. */
export function shade(value: unknown, scale: MatrixDocument['scale']): number | null {
  if (value === null || value === undefined) return null;
  const n = Number(value);
  if (n <= scale.min) return 0;
  const step = Math.ceil(((n - scale.min) / (scale.max - scale.min)) * scale.steps);
  return Math.min(scale.steps, Math.max(1, step));
}
