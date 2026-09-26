/**
 * The explanation dialog behind every chart and headline figure: the title,
 * the enlarged chart (when there is one) on its light mat, the "how to read
 * this" note, and the step-by-step methodology.
 *
 * A shadcn Dialog: Escape and the close button dismiss it, focus is trapped
 * inside while open and returns to the chart or figure that opened it. The
 * methodology is shown in full rather than folded away — the reader opened
 * the dialog to see how the number was made.
 */

import { useRef, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ZoomInIcon, ZoomOutIcon, ExternalLinkIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { emphasized } from '../markup';

export interface LightboxContent {
  /** Absent for text-only content (a KPI tile's explanation). */
  src?: string;
  alt: string;
  /** Heading; falls back to `alt`. */
  title?: string;
  note?: string;
  methodology?: string[];
}

export function ChartLightbox({
  content,
  onClose,
}: {
  content: LightboxContent;
  onClose: () => void;
}) {
  const [zoom, setZoom] = useState(1);
  const steps = content.methodology ?? [];
  // Radix returns focus to a DialogTrigger on close; this dialog is opened
  // from state (a chart or figure click), so it has none and focus would fall
  // to <body>. Remember what had focus when it opened and put it back.
  const returnFocus = useRef<HTMLElement | null>(null);
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        // A chart needs the room; a text-only explanation reads better narrow.
        className={
          content.src
            ? 'max-h-[92dvh] overflow-y-auto sm:max-w-[min(96vw,1400px)]'
            : 'max-h-[92dvh] overflow-y-auto sm:max-w-xl'
        }
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
          <DialogTitle className="text-base font-semibold">
            {content.title ?? content.alt}
          </DialogTitle>
        </DialogHeader>
        {content.src && (
          <div className="min-w-0">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2" aria-label="Chart zoom">
                <Button
                  variant="outline"
                  size="icon-sm"
                  aria-label="Zoom out"
                  disabled={zoom <= 1}
                  onClick={() => setZoom(Math.max(1, zoom - 0.5))}
                >
                  <ZoomOutIcon />
                </Button>
                <span className="w-12 text-center text-xs tabular-nums" aria-live="polite">
                  {Math.round(zoom * 100)}%
                </span>
                <Button
                  variant="outline"
                  size="icon-sm"
                  aria-label="Zoom in"
                  disabled={zoom >= 3}
                  onClick={() => setZoom(Math.min(3, zoom + 0.5))}
                >
                  <ZoomInIcon />
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setZoom(1)}>
                  Fit chart
                </Button>
              </div>
              <a
                href={content.src}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-xs text-link underline-offset-4 hover:underline"
              >
                Open original <ExternalLinkIcon className="size-3" />
              </a>
            </div>
            <div
              className="max-h-[65dvh] overflow-auto rounded-lg border bg-chart-ground"
              tabIndex={0}
              role="region"
              aria-label="Chart preview"
            >
              <img
                src={content.src}
                alt={content.alt}
                style={{ width: `${zoom * 100}%`, maxWidth: 'none' }}
                className="h-auto p-2"
              />
            </div>
          </div>
        )}
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
