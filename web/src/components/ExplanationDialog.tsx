/** The explanation behind a headline figure: its "how to read this" note and full methodology. */

import { useRef } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { emphasized } from '../markup';

export interface Explanation {
  title: string;
  note?: string;
  methodology?: string[];
}

export function ExplanationDialog({
  content,
  onClose,
}: {
  content: Explanation;
  onClose: () => void;
}) {
  const steps = content.methodology ?? [];
  // Opened from state, not a DialogTrigger, so Radix has nowhere to return focus;
  // remember the opener ourselves.
  const returnFocus = useRef<HTMLElement | null>(null);
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        className="max-h-[92dvh] overflow-y-auto sm:max-w-xl"
        // Without a note there is no DialogDescription for aria-describedby to point at.
        {...(!content.note && { 'aria-describedby': undefined })}
        onOpenAutoFocus={() => {
          returnFocus.current = document.activeElement as HTMLElement | null;
        }}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          returnFocus.current?.focus();
        }}
      >
        <DialogHeader className="pr-8">
          <DialogTitle className="text-base font-semibold">{content.title}</DialogTitle>
        </DialogHeader>
        {content.note && (
          <DialogDescription className="max-w-[80ch] text-sm/relaxed text-foreground">
            {emphasized(content.note)}
          </DialogDescription>
        )}
        {steps.length > 0 && (
          <section className="max-w-[80ch]">
            <h3 className="mb-1.5 text-xs font-semibold text-muted-foreground">
              Step-by-step methodology
            </h3>
            <ol className="flex list-decimal flex-col gap-1 pl-5 text-xs/relaxed">
              {steps.map((step) => (
                <li key={step}>{emphasized(step)}</li>
              ))}
            </ol>
          </section>
        )}
      </DialogContent>
    </Dialog>
  );
}
