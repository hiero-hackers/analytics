/**
 * One `key=value` pair of navigation state in the URL hash (tab, org, `widget`).
 * Writes add a history entry; view state uses urlState's `useUrlParam` instead.
 */

import { useUrlParam } from './urlState';

export function useHashState(key: string, fallback: string): [string, (value: string) => void] {
  const [value] = useUrlParam(key, fallback, { push: true });
  // Keeps an explicit value even when it equals the fallback: `#tab=Governance` stays once chosen.
  const update = (next: string) => {
    const params = new URLSearchParams(window.location.hash.slice(1));
    params.set(key, next);
    window.location.hash = params.toString();
  };
  return [value, update];
}
