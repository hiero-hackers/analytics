/**
 * A tab's collapsible section groups, and the on-page table of contents over
 * them. On wide screens the table of contents lives in the sidebar ("On this
 * page", see AppSidebar); on phones it is the sticky strip rendered here. Only
 * one of the two is ever mounted. With a single group, sections render bare —
 * a header and a contents list would both be redundant.
 */

import { ChevronDownIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
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
          <Collapsible
            defaultOpen
            key={entries[index].id}
            id={entries[index].id}
            className="group/section-group mt-6 scroll-mt-(--jump-h) first:mt-0"
          >
            {/* The Radix trigger styled directly: a quiet ruled heading row, not
                a button look (shadcn's Button paints its expanded state). */}
            <CollapsibleTrigger className="mb-3 flex w-full items-center gap-2 border-b py-2 text-left text-sm font-semibold outline-none hover:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring">
              <ChevronDownIcon
                aria-hidden="true"
                className="size-4 shrink-0 text-muted-foreground transition-transform group-data-[state=closed]/section-group:-rotate-90"
              />
              {name}
            </CollapsibleTrigger>
            <CollapsibleContent>{content}</CollapsibleContent>
          </Collapsible>
        ) : (
          <div key={anchorId(name, index)}>{content}</div>
        ),
      )}
    </>
  );
}
