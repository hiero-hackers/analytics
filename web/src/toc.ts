/**
 * The on-page table of contents over a tab's section groups — shared by the
 * groups themselves (their anchor ids), the sidebar's "On this page" list and
 * the phone strip, so all three agree on which id belongs to which group.
 */

import type { ReactNode } from 'react';

export type Group = [name: string, content: ReactNode];

/** One table-of-contents line: the group's anchor id and display name. */
export interface TocEntry {
  id: string;
  name: string;
}

// Position-qualified so two groups can never collide on a key or an anchor —
// distinct names can slug to the same string ("Roles & teams" / "Roles teams"),
// and a name could in principle repeat.
export const anchorId = (name: string, index: number) =>
  `grp-${index}-${name.replace(/\W+/g, '-')}`;

/** The table of contents for `groups` — empty when a single group renders bare. */
export function tocEntries(groups: Group[]): TocEntry[] {
  return groups.length > 1
    ? groups.map(([name], index) => ({ id: anchorId(name, index), name }))
    : [];
}

/**
 * Deliberately a scroll, NOT an <a href="#…">: the URL hash is the app's state
 * store (tab/org via useHashState), and fragment navigation would overwrite it
 * — resetting the active tab (#342). Scrolling leaves the hash alone.
 */
export function scrollToGroup(id: string) {
  document.getElementById(id)?.scrollIntoView();
}
