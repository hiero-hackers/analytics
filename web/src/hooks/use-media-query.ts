import { useSyncExternalStore } from 'react';

/** Whether a media query matches now, following changes. */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const list = window.matchMedia(query);
      list.addEventListener('change', onChange);
      return () => list.removeEventListener('change', onChange);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

/**
 * Below this width the header has no room for the freshness status, so the
 * page heading shows it instead — exactly one of the two, at every width.
 */
export const NARROW_HEADER = '(max-width: 1099px)';
