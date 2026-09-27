/**
 * Whether the page has scrolled and whether its title has passed under the
 * sticky header. The title is found by id because header and page are siblings.
 */

import { useSyncExternalStore } from 'react';

export const PAGE_TITLE_ID = 'page-title';

const SCROLLED = 1;
const TITLE_HIDDEN = 2;

function subscribe(onChange: () => void) {
  window.addEventListener('scroll', onChange, { passive: true });
  window.addEventListener('resize', onChange);
  return () => {
    window.removeEventListener('scroll', onChange);
    window.removeEventListener('resize', onChange);
  };
}

function snapshot(): number {
  const title = document.getElementById(PAGE_TITLE_ID);
  const header = document.querySelector('header');
  const edge = header?.getBoundingClientRect().bottom ?? 0;
  const hidden = !!title && title.getBoundingClientRect().bottom <= edge;
  return (window.scrollY > 4 ? SCROLLED : 0) | (hidden ? TITLE_HIDDEN : 0);
}

export function useHeaderScroll() {
  const state = useSyncExternalStore(subscribe, snapshot, () => 0);
  return { scrolled: Boolean(state & SCROLLED), titleHidden: Boolean(state & TITLE_HIDDEN) };
}
