/**
 * One chart's print preview. The chart is laid out as a sheet of paper at the
 * size it prints — only scaled down on screen — so the preview is the printout.
 * While the preview is open the page prints that sheet alone (print.css, chart
 * scope), on the paper size and orientation chosen here.
 */

import { useCallback, useEffect, useRef, useState, type ReactNode, type Ref } from 'react';
import { useElementSize, type ElementSize } from '@/hooks/use-element-size';
import { CircleAlertIcon, DownloadIcon, PrinterIcon, TriangleAlertIcon } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  bestOrientation,
  contentBox,
  MARGIN,
  pageRule,
  PAPERS,
  paperBox,
  PX_PER_MM,
  storedPaper,
  storePaper,
  type Orientation,
  type Paper,
} from '../../chartPrint';
import { exportName, exportSheet, FORMATS, saveBlob, type FileFormat } from '../../chartExport';
import { stamp } from '../../format';
import { PrintSheetContext } from '../../printContext';
import { VariantTabs } from '../VariantTabs';

/** The room a view has for its chart on the sheet, in CSS pixels. */
export type SheetBox = ElementSize;

/** Space between the sheet's header, chart and footer. */
const GAP = 14;
/** A chart never gets less height than this, even under a long header. */
const MIN_CHART = 200;
/** Header and footer heights until they are first measured. */
const HEADER_ESTIMATE = 150;
const FOOTER_ESTIMATE = 90;

const PAPER_ORDER: Paper[] = ['a4', 'letter'];
const ORIENTATIONS = ['auto', 'portrait', 'landscape'] as const;

interface SheetContent {
  title: string;
  /** Where the chart sits: organisation and card. */
  eyebrow: string;
  subtitle: string;
  /** The selection as `PrintFilter`s, and the switches that render as them. */
  filters: ReactNode;
  legend?: ReactNode;
  chart: (box: SheetBox) => ReactNode;
  /** Who is counted and over which window: always printed. */
  notes: ReactNode;
  /** How to read it and how it is measured: printed on request. */
  explanation?: ReactNode;
}

function Sheet({
  ref,
  paper,
  orientation,
  withExplanation,
  withDate,
  title,
  eyebrow,
  subtitle,
  filters,
  legend,
  chart,
  notes,
  explanation,
}: SheetContent & {
  ref: Ref<HTMLElement>;
  paper: Paper;
  orientation: Orientation;
  withExplanation: boolean;
  withDate: boolean;
}) {
  const content = contentBox(paper, orientation);
  const [headerRef, header] = useElementSize();
  const [footerRef, footer] = useElementSize();
  // When the preview opened: the moment this printout describes.
  const [printedAt] = useState(() => new Date().toISOString());
  const box = {
    width: Math.floor(content.width * PX_PER_MM),
    height: Math.max(
      MIN_CHART,
      Math.floor(
        content.height * PX_PER_MM -
          (header?.height ?? HEADER_ESTIMATE) -
          (footer?.height ?? FOOTER_ESTIMATE) -
          2 * GAP,
      ),
    ),
  };
  return (
    <article
      ref={ref}
      data-print-sheet
      className="flex flex-col"
      style={{ width: `${content.width}mm`, minHeight: `${content.height}mm`, gap: GAP }}
    >
      <header ref={headerRef} className="space-y-2">
        {eyebrow && (
          <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
            {eyebrow}
          </p>
        )}
        <div>
          <h1 className="font-display text-[20px] leading-tight font-semibold tracking-tight">
            {title}
          </h1>
          <p className="mt-0.5 text-[12px] text-muted-foreground">{subtitle}</p>
        </div>
        <PrintSheetContext.Provider value={{ title }}>
          <div data-print-filters className="flex flex-wrap gap-1.5">
            {filters}
          </div>
          {legend && <div data-print-legend-row>{legend}</div>}
        </PrintSheetContext.Provider>
      </header>
      <div data-print-chart className="min-w-0">
        <PrintSheetContext.Provider value={{ title }}>{chart(box)}</PrintSheetContext.Provider>
      </div>
      <footer
        ref={footerRef}
        className="mt-auto space-y-1 border-t pt-2 text-[10px] leading-snug text-muted-foreground"
      >
        {notes}
        {withExplanation && explanation}
        {withDate && <p>Printed {stamp(printedAt)} UTC</p>}
      </footer>
    </article>
  );
}

function Setting({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-medium">{label}</p>
      {children}
    </div>
  );
}

export function ChartPrintDialog({
  open,
  onOpenChange,
  onClosed,
  aspect,
  ...content
}: SheetContent & {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Return focus to the action that opened the preview (it has no DialogTrigger). */
  onClosed: () => void;
  /** The chart's natural width ÷ height: it picks the automatic orientation. */
  aspect: number;
}) {
  const [paper, setPaper] = useState<Paper>(storedPaper);
  const [choice, setChoice] = useState<(typeof ORIENTATIONS)[number]>('auto');
  // Off by default: a long methodology would take the chart's room. One click adds it.
  const [withExplanation, setWithExplanation] = useState(false);
  // Off by default too: the sheet already states when its data was generated.
  const [withDate, setWithDate] = useState(false);
  const [measureSheet, sheet] = useElementSize();
  // The sheet element itself, which Download renders to a file.
  const sheetNode = useRef<HTMLElement | null>(null);
  const sheetRef = useCallback(
    (element: HTMLElement | null) => {
      sheetNode.current = element;
      return measureSheet(element);
    },
    [measureSheet],
  );
  const [format, setFormat] = useState<FileFormat>('pdf');
  const [saving, setSaving] = useState(false);
  const [saveFailed, setSaveFailed] = useState(false);
  const [stageRef, stage] = useElementSize();
  const sheetHeight = sheet?.height ?? 0;
  const recommended = bestOrientation(aspect, paper);
  const orientation = choice === 'auto' ? recommended : choice;
  // Escape that dismisses the browser's print dialog must not close the preview too.
  const printingRef = useRef(false);

  // While open, printing (the button below, or the browser's own command) prints this sheet.
  useEffect(() => {
    if (!open) return;
    const root = document.documentElement;
    root.dataset.printScope = 'chart';
    const settle = () => requestAnimationFrame(() => (printingRef.current = false));
    window.addEventListener('afterprint', settle);
    return () => {
      delete root.dataset.printScope;
      window.removeEventListener('afterprint', settle);
    };
  }, [open]);

  const page = paperBox(paper, orientation);
  const pageWidth = page.width * PX_PER_MM;
  const pageHeight = page.height * PX_PER_MM;
  const contentHeight = contentBox(paper, orientation).height * PX_PER_MM;
  const margin = MARGIN * PX_PER_MM;
  // A tall selection (every row of a long ranking) runs on; the browser breaks it into pages.
  const pages = Math.max(1, Math.ceil(sheetHeight / contentHeight - 0.001));
  // The whole first page fits the stage's width and its height cap (64dvh, at most 680px).
  const stageCap = Math.min(window.innerHeight * 0.64, 680);
  const scale = stage
    ? Math.min(1, (stage.width - 32) / pageWidth, (stageCap - 32) / pageHeight)
    : 0.5;
  const frameHeight = Math.max(pageHeight, sheetHeight + 2 * margin);
  const paperName = `${PAPERS[paper].label} ${orientation}`;

  const print = async () => {
    await document.fonts?.ready;
    printingRef.current = true;
    window.print();
  };
  // A file made here, not by the print dialog: no browser header, footer or URL.
  const download = async () => {
    if (!sheetNode.current || saving) return;
    setSaving(true);
    setSaveFailed(false);
    try {
      const blob = await exportSheet(sheetNode.current, {
        format,
        paper,
        orientation,
        title: content.title,
      });
      saveBlob(blob, exportName(content.title, paper, orientation, format));
    } catch {
      setSaveFailed(true);
    } finally {
      setSaving(false);
    }
  };
  const formatLabel = FORMATS.find((option) => option.format === format)!.label;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-print-preview
        data-print-path
        className="max-h-[94dvh] overflow-y-auto sm:max-w-[min(96vw,1180px)]"
        onEscapeKeyDown={(event) => printingRef.current && event.preventDefault()}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          onClosed();
        }}
      >
        <style>{pageRule(paper, orientation)}</style>
        <DialogHeader data-print-chrome>
          <DialogTitle>Print preview</DialogTitle>
          <DialogDescription>
            {content.title} on {paperName} paper, {pages === 1 ? 'one page' : `${pages} pages`}. The
            chart prints exactly as shown, with the selection it has on the dashboard.
          </DialogDescription>
        </DialogHeader>
        <div data-print-path className="grid min-w-0 gap-4 md:grid-cols-[minmax(0,1fr)_15rem]">
          <div
            ref={stageRef}
            data-print-path
            className="max-h-[min(64dvh,680px)] min-w-0 overflow-auto rounded-lg bg-muted p-4"
          >
            {/* The page, scaled to fit; inert so its chart is not a second set of controls. */}
            <div
              data-print-path
              inert
              className="relative mx-auto bg-paper shadow-md ring-1 ring-foreground/10"
              style={{ width: pageWidth * scale, height: frameHeight * scale }}
            >
              <div
                data-print-path
                data-print-scale
                className="origin-top-left"
                style={{ width: pageWidth, padding: margin, transform: `scale(${scale})` }}
              >
                <Sheet
                  {...content}
                  ref={sheetRef}
                  paper={paper}
                  orientation={orientation}
                  withExplanation={withExplanation}
                  withDate={withDate}
                />
              </div>
              {Array.from({ length: pages - 1 }, (_, index) => (
                <div
                  key={index}
                  data-print-chrome
                  aria-hidden="true"
                  className="absolute inset-x-0 border-t border-dashed border-link"
                  style={{ top: (margin + (index + 1) * contentHeight) * scale }}
                />
              ))}
            </div>
          </div>
          <div data-print-chrome className="space-y-4">
            <Setting label="Paper size">
              <VariantTabs
                appearance="segmented"
                labels={PAPER_ORDER.map((option) => PAPERS[option].label)}
                active={PAPER_ORDER.indexOf(paper)}
                onSelect={(index) => {
                  setPaper(PAPER_ORDER[index]);
                  storePaper(PAPER_ORDER[index]);
                }}
                ariaLabel="Paper size"
              />
            </Setting>
            <Setting label="Orientation">
              <VariantTabs
                appearance="segmented"
                labels={['Best fit', 'Portrait', 'Landscape']}
                active={ORIENTATIONS.indexOf(choice)}
                onSelect={(index) => setChoice(ORIENTATIONS[index])}
                ariaLabel="Orientation"
              />
              <p className="text-xs text-muted-foreground">
                Best fit is {recommended}: it gives this chart the most room.
              </p>
            </Setting>
            {content.explanation && (
              <Setting label="How to read it and methodology">
                <VariantTabs
                  appearance="segmented"
                  labels={['Include', 'Leave out']}
                  active={withExplanation ? 0 : 1}
                  onSelect={(index) => setWithExplanation(index === 0)}
                  ariaLabel="How to read it and methodology"
                />
              </Setting>
            )}
            <Setting label="Printed date">
              <VariantTabs
                appearance="segmented"
                labels={['Include', 'Leave out']}
                active={withDate ? 0 : 1}
                onSelect={(index) => setWithDate(index === 0)}
                ariaLabel="Printed date"
              />
            </Setting>
            <Setting label="Save as">
              <VariantTabs
                appearance="segmented"
                labels={FORMATS.map((option) => option.label)}
                active={FORMATS.findIndex((option) => option.format === format)}
                onSelect={(index) => setFormat(FORMATS[index].format)}
                ariaLabel="File type"
              />
              <p className="text-xs text-muted-foreground">
                {format === 'pdf'
                  ? `One ${PAPERS[paper].label} page per printed page.`
                  : `The whole sheet as one image, at print resolution.`}
              </p>
            </Setting>
            {saveFailed && (
              <Alert variant="destructive">
                <CircleAlertIcon />
                <AlertTitle>Could not create the {formatLabel} file.</AlertTitle>
                <AlertDescription>Try again, or use Print instead.</AlertDescription>
              </Alert>
            )}
            {pages > 1 && (
              <p
                role="status"
                className="flex gap-1.5 rounded-md border border-dashed px-2.5 py-2 text-xs text-warn-ink"
              >
                <TriangleAlertIcon aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
                This selection needs {pages} pages. Portrait, or fewer rows on the dashboard, can
                fit it on one.
              </p>
            )}
            <p className="text-xs leading-relaxed text-muted-foreground">
              Download saves exactly this page as a file. Print sends it to your browser’s print
              dialog: keep the paper at {paperName} and the scale at 100%.
            </p>
          </div>
        </div>
        <DialogFooter data-print-chrome>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="outline" disabled={saving} onClick={() => void download()}>
            <DownloadIcon data-icon="inline-start" />
            {saving ? `Saving ${formatLabel}…` : `Download ${formatLabel}`}
          </Button>
          <Button onClick={() => void print()}>
            <PrinterIcon data-icon="inline-start" />
            Print
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
