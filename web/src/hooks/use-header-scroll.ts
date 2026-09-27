/**
 * What the sticky header needs to know about the page's scroll position:
 * whether the page has scrolled at all (the header lifts off the content),
 * and whether the page title has passed under the header (the header then
 * names the page itself, so the reader never loses where they are).
 *
 * One snapshot for both, read on scroll and resize. The title is found by id
 * rather than by ref because the header and the page are siblings.
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
