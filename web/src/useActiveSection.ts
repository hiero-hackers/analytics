/**
 * Scroll-spy for the on-page table of contents: which of `ids` the reader is
 * currently in. A section counts as current once its top has scrolled up into
 * the band just below the sticky header; the last such section wins, so a long
 * section stays current while its body fills the screen.
 *
 * Without IntersectionObserver (old browsers, jsdom) nothing is highlighted —
 * the table of contents still works, it just doesn't track.
 */

import { useEffect, useState } from 'react';

/** Band below the sticky header (and mobile strip) where a heading becomes "current". */
const ROOT_MARGIN = '-110px 0px -55% 0px';

export function useActiveSection(ids: string[]): string | null {
  const [active, setActive] = useState<string | null>(null);
  const key = ids.join('\n');

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined' || ids.length === 0) return;
    const elements = ids
      .map((id) => document.getElementById(id))
      .filter((el): el is HTMLElement => el !== null);
    const observer = new IntersectionObserver(
      () => {
        // Recompute from positions rather than trusting the entry list: it only
        // carries the elements whose intersection changed.
        const passed = elements.filter(
          (el) => el.getBoundingClientRect().top <= window.innerHeight * 0.45,
        );
        setActive(passed.length ? passed[passed.length - 1].id : (elements[0]?.id ?? null));
      },
      { rootMargin: ROOT_MARGIN, threshold: [0, 1] },
    );
    for (const el of elements) observer.observe(el);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` is ids' identity
  }, [key]);

  return ids.includes(active ?? '') ? active : null;
}
