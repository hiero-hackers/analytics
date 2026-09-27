/**
 * The explanation dialog behind every headline figure: the title, the "how to
 * read this" note, and the step-by-step methodology. Charts carry the same
 * text in their own footer, so this dialog never shows a chart.
 *
 * A shadcn Dialog: Escape and the close button dismiss it, focus is trapped
 * inside while open and returns to the figure that opened it. The methodology
 * is shown in full rather than folded away — the reader opened the dialog to
 * see how the number was made.
 */

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
  // Radix returns focus to a DialogTrigger on close; this dialog is opened
  // from state (a figure click), so it has none and focus would fall to
  // <body>. Remember what had focus when it opened and put it back.
  const returnFocus = useRef<HTMLElement | null>(null);
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        className="max-h-[92dvh] overflow-y-auto sm:max-w-xl"
        // Radix wires aria-describedby to DialogDescription; without a note
        // there is none, so say so rather than point at nothing.
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
