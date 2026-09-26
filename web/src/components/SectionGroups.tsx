/**
 * A tab's collapsible section groups, and the on-page table of contents over
 * them. On wide screens the table of contents lives in the sidebar ("On this
 * page", see AppSidebar); on phones it is the sticky strip rendered here. Only
 * one of the two is ever mounted. With a single group, sections render bare —
 * a header and a contents list would both be redundant.
 */

import { Button } from '@/components/ui/button';
import { useIsMobile } from '@/hooks/use-mobile';
import { anchorId, scrollToGroup, tocEntries, type Group, type TocEntry } from '../toc';
import { useActiveSection } from '../useActiveSection';

/** The phone table of contents: a sticky strip under the header that scrolls sideways. */
export function GroupStrip({ entries }: { entries: TocEntry[] }) {
  const active = useActiveSection(entries.map((entry) => entry.id));
  return (
    <nav
      aria-label="Jump to"
      className="sticky top-13 z-10 -mx-3 mb-2 flex gap-1 overflow-x-auto border-b bg-background px-3 py-2 min-[600px]:-mx-4 min-[600px]:px-4"
    >
      {entries.map((entry) => (
        <Button
          key={entry.id}
          type="button"
          size="sm"
          variant={entry.id === active ? 'secondary' : 'ghost'}
          aria-current={entry.id === active ? 'location' : undefined}
          onClick={() => scrollToGroup(entry.id)}
        >
          {entry.name}
        </Button>
      ))}
    </nav>
  );
}

export function SectionGroups({ groups }: { groups: Group[] }) {
  const isMobile = useIsMobile();
  const entries = tocEntries(groups);
  return (
    <>
      {isMobile && entries.length > 0 && <GroupStrip entries={entries} />}
      {groups.map(([name, content], index) =>
        entries.length > 0 ? (
          <details className="group" id={entries[index].id} open key={entries[index].id}>
            <summary className="grouphdr">{name}</summary>
            {content}
          </details>
        ) : (
          <div key={anchorId(name, index)}>{content}</div>
        ),
      )}
    </>
  );
}
