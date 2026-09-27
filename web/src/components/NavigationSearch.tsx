import { useEffect, useRef, useState } from 'react';
import { ArrowUpRightIcon, SearchIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import type { NavModel } from '../nav';
import { scrollToGroup, type TocEntry } from '../toc';

/** A small navigation finder: searches real pages and the current page's sections. */
export function NavigationSearch({
  nav,
  toc,
  onTab,
}: {
  nav: NavModel | null;
  toc: TocEntry[];
  onTab: (tab: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const handle = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setOpen((current) => !current);
      }
    };
    window.addEventListener('keydown', handle);
    return () => window.removeEventListener('keydown', handle);
  }, []);
  const results = [
    ...(nav?.macros ?? []).map((name) => ({
      id: `page-${name}`,
      name,
      kind: 'Page',
      action: () => {
        onTab(name);
        window.scrollTo({ top: 0, behavior: 'instant' });
      },
    })),
    ...toc.map((entry) => ({
      ...entry,
      kind: 'On this page',
      action: () => scrollToGroup(entry.id),
    })),
  ].filter((entry) => entry.name.toLowerCase().includes(query.trim().toLowerCase()));
  const choose = (action: () => void) => {
    setOpen(false);
    setQuery('');
    requestAnimationFrame(action);
  };
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setQuery('');
      }}
    >
      <DialogTrigger asChild>
        <Button
          ref={trigger}
          variant="outline"
          aria-label="Search dashboard"
          aria-keyshortcuts="Control+k Meta+k"
          className="h-9 gap-2 rounded-lg bg-background px-2.5 text-muted-foreground shadow-none lg:w-56 lg:justify-start"
        >
          <SearchIcon className="size-4" />
          <span className="hidden lg:inline">Find a section…</span>
          <kbd
            aria-hidden="true"
            className="ml-auto hidden rounded border bg-card px-1.5 py-0.5 text-[10px] lg:inline"
          >
            ⌘ K
          </kbd>
        </Button>
      </DialogTrigger>
      <DialogContent
        className="gap-0 overflow-hidden p-0 sm:max-w-lg"
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          trigger.current?.focus();
        }}
      >
        <DialogHeader className="border-b p-5">
          <DialogTitle>Explore the dashboard</DialogTitle>
          <DialogDescription>Find a page or jump to a section.</DialogDescription>
        </DialogHeader>
        <div className="relative m-4">
          <SearchIcon
            aria-hidden="true"
            className="absolute left-3 top-3 size-4 text-muted-foreground"
          />
          <Input
            autoFocus
            aria-label="Search pages and sections"
            placeholder="Contributors, governance, releases…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && results[0]) choose(results[0].action);
            }}
            className="h-10 bg-background pl-9"
          />
        </div>
        <div
          className="max-h-[min(55dvh,360px)] overflow-y-auto px-3 pb-3"
          aria-label="Search results"
        >
          {results.length ? (
            results.map((entry) => (
              <button
                key={entry.id}
                type="button"
                onClick={() => choose(entry.action)}
                className="group flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left text-sm outline-none hover:bg-muted focus-visible:bg-muted focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="flex-1">{entry.name}</span>
                <span className="text-[11px] text-muted-foreground">{entry.kind}</span>
                <ArrowUpRightIcon aria-hidden="true" className="size-4 text-muted-foreground" />
              </button>
            ))
          ) : (
            <p role="status" className="p-6 text-center text-sm text-muted-foreground">
              No sections match “{query}”.
            </p>
          )}
        </div>
        <div className="border-t bg-muted/40 px-5 py-3 text-xs text-muted-foreground">
          Enter opens the first result · Tab moves between results · Esc closes
        </div>
      </DialogContent>
    </Dialog>
  );
}
