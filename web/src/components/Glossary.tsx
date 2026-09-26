/**
 * The tab's "how to read this" explainer, rendered from the manifest's
 * term/definition data and folded away by default. Definitions may mark
 * emphasis with *asterisks* — the only inline markup the glossary contract
 * allows.
 */

import { Fragment } from 'react';
import { ChevronRightIcon } from 'lucide-react';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import type { Glossary as GlossaryData } from '../api';
import { emphasized } from '../markup';

export function Glossary({ glossary }: { glossary: GlossaryData }) {
  return (
    <Collapsible className="group/glossary mb-6 rounded-lg border bg-card">
      {/* The Radix trigger styled directly, not a shadcn Button: this is a
          disclosure row, and Button paints its expanded state as a filled bar. */}
      <CollapsibleTrigger className="flex h-9 w-full items-center gap-2 rounded-lg px-3 text-left text-xs font-medium outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring">
        <ChevronRightIcon
          aria-hidden="true"
          className="size-3.5 shrink-0 text-muted-foreground transition-transform group-data-[state=open]/glossary:rotate-90"
        />
        {glossary.title}
      </CollapsibleTrigger>
      {/* Mounted while closed (as <details> was), just not displayed — the
          terms stay in the document. forceMount makes Radix skip its own
          `hidden`, hence the explicit data-state rule. */}
      <CollapsibleContent
        forceMount
        className="px-4 pt-1 pb-4 text-xs/relaxed data-[state=closed]:hidden"
      >
        {glossary.layout === 'notes' ? (
          // Interpretation notes (e.g. the HIPs tab's HIP-1 reading rules):
          // bolded lead-ins with prose, not the term/definition grid.
          <ul className="flex max-w-[85ch] list-disc flex-col gap-2 pl-4 text-muted-foreground">
            {glossary.terms.map(({ term, definition }) => (
              <li key={term}>
                <strong className="font-semibold text-foreground">{term}</strong>{' '}
                {emphasized(definition)}
              </li>
            ))}
          </ul>
        ) : (
          <>
            <dl className="grid grid-cols-[minmax(0,9.5rem)_1fr] gap-x-4 gap-y-1.5">
              {glossary.terms.map(({ term, definition }) => (
                <Fragment key={term}>
                  <dt className="font-semibold">{term}</dt>
                  <dd className="text-muted-foreground">{emphasized(definition)}</dd>
                </Fragment>
              ))}
            </dl>
            {glossary.note && <p className="mt-3 text-soft">{glossary.note}</p>}
          </>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
