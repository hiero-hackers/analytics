/**
 * The URL hash as a small shared store — the app's only router and the home
 * of every piece of view state worth sharing.
 *
 * Two kinds of write:
 * - navigation (`push`): tab and org changes add a history entry, so Back
 *   returns to the previous tab exactly as before;
 * - view state (the default, `replace`): a chart's tab, search box, hidden
 *   series or focus rewrite the current entry, so typing in a search box does
 *   not bury Back under a hundred entries — yet "Copy link" still captures it.
 *
 * `replaceState` fires no `hashchange`, so writes notify subscribers directly;
 * the browser's own hash changes (Back, a pasted link) arrive via `hashchange`.
 * A value equal to its fallback is removed, keeping shared URLs short.
 */

import { useSyncExternalStore } from 'react';

const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener('hashchange', listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener('hashchange', listener);
  };
}

const snapshot = () => window.location.hash;

export function readParam(key: string, fallback = ''): string {
  return new URLSearchParams(window.location.hash.slice(1)).get(key) ?? fallback;
}

/** Set (or, for null/empty, remove) several keys in one history update. */
export function writeParams(
  updates: Record<string, string | null | undefined>,
  { push = false }: { push?: boolean } = {},
) {
  const params = new URLSearchParams(window.location.hash.slice(1));
  for (const [key, value] of Object.entries(updates)) {
    if (value === null || value === undefined || value === '') params.delete(key);
    else params.set(key, value);
  }
  const hash = params.toString();
  if (hash === window.location.hash.slice(1)) return;
  if (push) {
    window.location.hash = hash;
  } else {
    const url = `${window.location.pathname}${window.location.search}${hash ? `#${hash}` : ''}`;
    window.history.replaceState(window.history.state, '', url);
  }
  for (const listener of listeners) listener();
}

/**
 * One hash key as React state. `fallback` is what an absent key means, and
 * writing the fallback removes the key again.
 */
export function useUrlParam(
  key: string,
  fallback = '',
  options: { push?: boolean } = {},
): [string, (value: string) => void] {
  useSyncExternalStore(subscribe, snapshot, snapshot);
  const value = readParam(key, fallback);
  const set = (next: string) => writeParams({ [key]: next === fallback ? null : next }, options);
  return [value, set];
}

/** A comma-separated list held in one key (e.g. hidden series). */
export function useUrlList(key: string): [string[], (value: string[]) => void] {
  const [raw, setRaw] = useUrlParam(key);
  return [raw ? raw.split(',') : [], (value) => setRaw(value.join(','))];
}

/** A small integer held in one key (a tab or slide index). */
export function useUrlIndex(key: string): [number, (value: number) => void] {
  const [raw, setRaw] = useUrlParam(key, '0');
  const parsed = Number.parseInt(raw, 10);
  return [
    Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : 0,
    (value) => setRaw(String(value)),
  ];
}

/** A boolean flag held in one key ("1" when on, absent when off). */
export function useUrlFlag(key: string): [boolean, (value: boolean) => void] {
  const [raw, setRaw] = useUrlParam(key);
  return [raw === '1', (value) => setRaw(value ? '1' : '')];
}
