/** A tab's section-group table of contents, shared by the groups, sidebar and phone strip. */

import type { ReactNode } from 'react';

export type Group = [name: string, content: ReactNode];

export interface TocEntry {
  id: string;
  name: string;
}

// Position-qualified: distinct names can slug alike ("Roles & teams" / "Roles teams").
export const anchorId = (name: string, index: number) =>
  `grp-${index}-${name.replace(/\W+/g, '-')}`;

/** The table of contents for `groups` — empty when a single group renders bare. */
export function tocEntries(groups: Group[]): TocEntry[] {
  return groups.length > 1
    ? groups.map(([name], index) => ({ id: anchorId(name, index), name }))
    : [];
}

/** A scroll, not an <a href="#…">: fragment navigation would overwrite the hash state (#342). */
export function scrollToGroup(id: string) {
  document.getElementById(id)?.scrollIntoView();
}
