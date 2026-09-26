/**
 * The dashboard-wide focus: one repository, contributor, organisation or team
 * held in the URL (`focus=repo:hiero-sdk-js`). Clicking a bar, a heatmap row
 * or a network node sets it; every table with that column filters to it, and
 * every chart with that dimension highlights it. Charts and tables without
 * the dimension are left alone and say so — a focus never implies filtering
 * a dataset cannot do.
 */

import { useUrlParam } from './urlState';

export type FocusDimension = 'repo' | 'contributor' | 'organisation' | 'team';

export interface Focus {
  dimension: FocusDimension;
  value: string;
}

export const DIMENSION_LABELS: Record<FocusDimension, string> = {
  repo: 'repository',
  contributor: 'contributor',
  organisation: 'organisation',
  team: 'team',
};

/** Column or dimension keys the datasets use, mapped to the focus they carry. */
const KEYS: Record<string, FocusDimension> = {
  repo: 'repo',
  repository: 'repo',
  contributor: 'contributor',
  'contributor name': 'contributor',
  login: 'contributor',
  user: 'contributor',
  organisation: 'organisation',
  team: 'team',
};

/** The focus a column (or document dimension) carries, if any. */
export function dimensionOf(key: string): FocusDimension | null {
  return KEYS[key] ?? null;
}

/**
 * One comparable form per value: repositories drop an `owner/` prefix (the
 * tables keep it, the charts do not), and every dimension ignores case.
 */
export function normalise(dimension: FocusDimension, value: unknown): string {
  const text = String(value ?? '')
    .trim()
    .toLowerCase();
  return dimension === 'repo' ? (text.split('/').pop() ?? text) : text;
}

export function matches(focus: Focus | null, dimension: FocusDimension | null, value: unknown) {
  return !!focus && focus.dimension === dimension && normalise(dimension, value) === focus.value;
}

function parse(raw: string): Focus | null {
  const at = raw.indexOf(':');
  if (at <= 0) return null;
  const dimension = raw.slice(0, at) as FocusDimension;
  const value = raw.slice(at + 1);
  return dimension in DIMENSION_LABELS && value
    ? { dimension, value: normalise(dimension, value) }
    : null;
}

export function useFocus(): [Focus | null, (next: Focus | null) => void] {
  const [raw, setRaw] = useUrlParam('focus');
  const set = (next: Focus | null) =>
    setRaw(next ? `${next.dimension}:${normalise(next.dimension, next.value)}` : '');
  return [parse(raw), set];
}

/** Focus on `value`, or clear the focus when it is already the focus. */
export function toggle(
  focus: Focus | null,
  dimension: FocusDimension,
  value: unknown,
): Focus | null {
  return matches(focus, dimension, value)
    ? null
    : { dimension, value: normalise(dimension, value) };
}
