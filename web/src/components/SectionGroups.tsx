/**
 * A tab's collapsible section groups, plus the phone table of contents (the
 * sidebar holds it on wide screens). A single group renders bare.
 */

import { useState, type ReactNode } from 'react';
import { ChevronDownIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { useIsMobile } from '@/hooks/use-mobile';
import { usePrintMode } from '../printContext';
import { anchorId, scrollToGroup, tocEntries, type Group, type TocEntry } from '../toc';
import { useActiveSection } from '../useActiveSection';

/** Sticky, sideways-scrolling strip under the header. */
export function GroupStrip({ entries }: { entries: TocEntry[] }) {
  const active = useActiveSection(entries.map((entry) => entry.id));
  return (
    <nav
      data-print-hide
      data-scroll-restore
      aria-label="Jump to"
      className="sticky top-(--header-h) z-10 -mx-3 mb-2 flex gap-1 overflow-x-auto border-b bg-background px-3 py-2 min-[600px]:-mx-4 min-[600px]:px-4"
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

/** One named group. Paper opens it and states its name as a heading; a
 *  reader's collapse is kept and returns after printing. */
function SectionGroup({ id, name, children }: { id: string; name: string; children: ReactNode }) {
  const printing = usePrintMode();
  const [open, setOpen] = useState(true);
  return (
    <Collapsible
      open={printing || open}
      onOpenChange={setOpen}
      id={id}
      className="group/section-group mt-6 scroll-mt-(--jump-h) first:mt-0"
    >
      {printing && <h2 className="print-group">{name}</h2>}
      {/* Radix trigger, not shadcn's Button, which paints its expanded state. */}
      <CollapsibleTrigger
        hidden={printing}
        data-print-hide
        className="mb-3 flex w-full items-center gap-2 border-b py-2 text-left text-sm font-semibold outline-none hover:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
      >
        <ChevronDownIcon
          aria-hidden="true"
          className="size-4 shrink-0 text-muted-foreground transition-transform group-data-[state=closed]/section-group:-rotate-90"
        />
        {name}
      </CollapsibleTrigger>
      <CollapsibleContent>{children}</CollapsibleContent>
    </Collapsible>
  );
}

export function SectionGroups({ groups }: { groups: Group[] }) {
  const printing = usePrintMode();
  const isMobile = useIsMobile();
  const entries = tocEntries(groups);
  return (
    <>
      {isMobile && entries.length > 0 && <GroupStrip entries={entries} />}
      {groups.map(([name, content], index) =>
        entries.length > 0 ? (
          <SectionGroup key={entries[index].id} id={entries[index].id} name={name}>
            {content}
          </SectionGroup>
        ) : (
          <div key={anchorId(name, index)}>
            {/* A lone group has no header on screen; paper still names it. */}
            {printing && name && <h2 className="print-group">{name}</h2>}
            {content}
          </div>
        ),
      )}
    </>
  );
}
