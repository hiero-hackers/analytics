/** Classifies a headline figure's value so a stat tile can draw it as that kind of number. */

import type { MetricTile } from './api';

const count = new Intl.NumberFormat('en-US');

export type Figure =
  | { kind: 'share'; value: string; percent: number }
  | { kind: 'part'; value: string; of: string; percent: number }
  | { kind: 'count'; value: string }
  | { kind: 'text'; value: string };

export function readFigure(value: MetricTile['value']): Figure {
  if (typeof value === 'number') return { kind: 'count', value: count.format(value) };
  const text = value.trim();
  const share = /^(\d+(?:\.\d+)?)\s*%$/.exec(text);
  if (share) return { kind: 'share', value: share[1], percent: Math.min(100, Number(share[1])) };
  const part = /^([\d,]+)\s+of\s+([\d,]+)$/.exec(text);
  if (part) {
    const [n, d] = [Number(part[1].replace(/,/g, '')), Number(part[2].replace(/,/g, ''))];
    if (d > 0)
      return {
        kind: 'part',
        value: count.format(n),
        of: count.format(d),
        percent: Math.min(100, (n / d) * 100),
      };
  }
  if (/^\d+$/.test(text)) return { kind: 'count', value: count.format(Number(text)) };
  return { kind: 'text', value: text };
}
