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

/** Below this width the page heading shows the freshness status instead of the header. */
export const NARROW_HEADER = '(max-width: 1099px)';
