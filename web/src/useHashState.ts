/**
 * One `key=value` pair of navigation state held in the URL hash (tab, org,
 * the shared-link `widget`). Writes add a history entry, so Back undoes a tab
 * change. View state that should not (a chart's search box, hidden series,
 * the focus) uses `useUrlParam` from urlState, which shares the same store.
 */

import { useUrlParam } from './urlState';

export function useHashState(key: string, fallback: string): [string, (value: string) => void] {
  const [value] = useUrlParam(key, fallback, { push: true });
  // Navigation keeps an explicit value even when it equals the fallback, as
  // before: `#tab=Governance` stays in the URL once chosen.
  const update = (next: string) => {
    const params = new URLSearchParams(window.location.hash.slice(1));
    params.set(key, next);
    window.location.hash = params.toString();
  };
  return [value, update];
}
