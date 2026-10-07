/**
 * The frame every interactive chart shares: heading, Chart / Data switch, CSV,
 * print preview, expanded dialog and explanatory footer. Views build the chart,
 * table, CSV and printed sheet from one selection, so the four can never disagree.
 */

import { lazy, Suspense, useContext, useRef, useState, type ReactNode } from 'react';
import { ChartLeading, ChartSectionTitle } from './leading';
import { CrosshairIcon, Maximize2Icon, PrinterIcon, XIcon } from 'lucide-react';
import { Alert, AlertAction, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import type { ChartDocumentMeta, Manifest } from '../../api';
import type { CsvExport } from '../../csv';
import { DIMENSION_LABELS, dimensionOf, useFocus } from '../../focus';
import { stamp } from '../../format';
import { OrgContext } from '../../orgContext';
import { usePrintMode } from '../../printContext';
import { useUrlIndex } from '../../urlState';
import { CsvDownloadButton } from '../CsvDownloadButton';
import { PrintFilter } from '../PrintFilter';
import { VariantTabs } from '../VariantTabs';
import type { SheetBox } from './ChartPrintDialog';

// Loaded when a reader first opens a print preview.
const ChartPrintDialog = lazy(() =>
  import('./ChartPrintDialog').then((module) => ({ default: module.ChartPrintDialog })),
);

export type { SheetBox };

/** A selection the printed sheet states that no switch shows: a search, hidden series, a span. */
export interface PrintFilterSpec {
  label: string;
  value: string;
}

export interface ViewProps<T> {
  data: T;
  title: string;
  period: string;
  provenance: Manifest['provenance'];
  /** More height than its peers: rankings may show more rows before "Show all". */
  roomy?: boolean;
}

export function ChartShell({
  data,
  title,
  period,
  provenance,
  subtitle,
  toolbar,
  controls,
  chart,
  table,
  csv,
  windowNote,
  empty,
  emptyText = 'No data is available for this selection.',
  focusFound = true,
  printFilters = [],
  printAspect = 2,
}: ViewProps<ChartDocumentMeta> & {
  subtitle: string;
  /** Segmented settings (mark, scale, span, cohort), shown for chart and table alike. */
  toolbar?: ReactNode;
  /** Series toggles, search or comparisons under the toolbar, for chart and table alike. */
  controls?: ReactNode;
  /** The chart itself; `sheet` is its room on the printed page when drawing the print preview. */
  chart: (expanded: boolean, sheet?: SheetBox) => ReactNode;
  table: ReactNode;
  csv: () => Omit<CsvExport, 'total' | 'dataAsOf'>;
  windowNote: string;
  empty: boolean;
  emptyText?: string;
  /** Whether the focused value appears in this chart (when it has the dimension). */
  focusFound?: boolean;
  /** Printed as filters beside the switches' own choices. */
  printFilters?: (PrintFilterSpec | false | null | undefined)[];
  /** The chart's natural width ÷ height, which picks the printed orientation. */
  printAspect?: number;
}) {
  // Chart / Data lives in the URL, so a shared link opens the same view.
  const [view, setView] = useUrlIndex(`${data.id}.view`);
  const [focus, setFocus] = useFocus();
  const supported = focus ? data.dimensions.some((d) => dimensionOf(d) === focus.dimension) : false;
  const [expanded, setExpanded] = useState(false);
  const printing = usePrintMode();
  const leading = useContext(ChartLeading);
  const expandRef = useRef<HTMLButtonElement>(null);
  const printRef = useRef<HTMLButtonElement>(null);
  const org = useContext(OrgContext);
  const section = useContext(ChartSectionTitle);
  const [previewing, setPreviewing] = useState(false);
  // The URL at the moment Print found nothing to print: every selection lives
  // there, so the message stands until the reader changes one.
  const [nothingAt, setNothingAt] = useState<string | null>(null);
  const nothingToPrint = empty && nothingAt === window.location.hash;
  const heading = period !== title ? `${title} · ${period}` : title;
  // Lead with the unit, dropping a first part that merely repeats it ("Maintainers" vs "Maintainers (share …)").
  const unit = data.unit.toLowerCase();
  const parts = subtitle.split(' · ').filter(Boolean);
  const detail = parts[0]?.toLowerCase().startsWith(unit)
    ? subtitle
    : [
        data.unit,
        ...(parts[0] && unit.startsWith(parts[0].toLowerCase()) ? parts.slice(1) : parts),
      ].join(' · ');
  const freshness = data.generated_at
    ? `Source generated ${stamp(data.generated_at)} UTC${data.stale ? ' · older than the scheduled refresh' : ''}`
    : 'Source freshness is unavailable.';
  // Skip the freshness line when the window note (a snapshot) already states that time.
  const showFreshness =
    !data.generated_at || data.stale || !windowNote.includes(stamp(data.generated_at));

  const content = (
    // A container, so the toolbar can drop its labels in a narrow card.
    <div className="@container min-w-0 space-y-3.5">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
        <div className="min-w-0">
          {/* The dialog's own title already names the chart. */}
          {!expanded && <p className="text-sm font-semibold">{title}</p>}
          <p className="mt-1 text-xs text-muted-foreground">{detail}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* Chart/Data says nothing on paper; the printed view is self-evident. */}
          <VariantTabs
            printSelection={false}
            appearance="segmented"
            labels={['Chart', 'Data']}
            active={view}
            onSelect={setView}
            ariaLabel={`${title} display`}
          />
          <CsvDownloadButton
            compact={!expanded}
            provenance={provenance}
            payload={() => {
              const source = csv();
              return { ...source, total: source.rows.length, dataAsOf: data.generated_at };
            }}
          />
          <Button
            ref={printRef}
            variant="outline"
            size="sm"
            aria-label={`Print chart: ${title}`}
            title="Print chart"
            onClick={() => {
              if (empty) {
                setNothingAt(window.location.hash);
              } else {
                setNothingAt(null);
                setPreviewing(true);
              }
            }}
          >
            <PrinterIcon /> <span className="hidden @lg:inline">Print</span>
          </Button>
          {!expanded && (
            <Button
              ref={expandRef}
              variant="outline"
              size="sm"
              aria-label={`Expand interactive chart: ${title}`}
              title="Expand"
              onClick={() => setExpanded(true)}
            >
              <Maximize2Icon /> <span className="hidden @lg:inline">Expand</span>
            </Button>
          )}
        </div>
      </div>
      {(leading || toolbar) && (
        <div
          role="group"
          aria-label={`${title} settings`}
          className="flex flex-wrap items-center gap-2"
        >
          {leading}
          {toolbar}
        </div>
      )}
      {nothingToPrint && (
        <Alert data-print-hide>
          <PrinterIcon />
          <AlertTitle>Nothing to print for this selection</AlertTitle>
          <AlertDescription>
            {emptyText} Choose another period or view, show a hidden series, or clear the search or
            focus, then print again.
          </AlertDescription>
          <AlertAction>
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label="Dismiss"
              onClick={() => setNothingAt(null)}
            >
              <XIcon />
            </Button>
          </AlertAction>
        </Alert>
      )}
      {controls}
      {focus && (!supported || !focusFound) && (
        <p className="flex flex-wrap items-center gap-2 rounded-md border border-dashed px-3 py-2 text-xs text-muted-foreground">
          <CrosshairIcon className="size-3.5" aria-hidden="true" />
          {supported
            ? `${focus.value} does not appear in this chart.`
            : `Shows the whole organisation: this chart has no ${DIMENSION_LABELS[focus.dimension]} breakdown, so the focus on ${focus.value} does not apply.`}
          <Button
            variant="link"
            size="sm"
            className="h-auto p-0 text-xs"
            onClick={() => setFocus(null)}
          >
            Clear focus
          </Button>
        </p>
      )}
      {empty ? (
        <p className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
          {emptyText}
        </p>
      ) : view === 0 ? (
        chart(expanded)
      ) : (
        table
      )}
      <div className="border-t pt-4 text-xs leading-relaxed text-muted-foreground">
        <p>{data.population}</p>
        <p className="mt-2">{windowNote}</p>
        {showFreshness && <p className={data.stale ? 'mt-1 text-warn-ink' : 'mt-1'}>{freshness}</p>}
        {data.note || data.methodology?.length ? (
          <details className="mt-3">
            <summary className="cursor-pointer font-medium text-foreground">
              {data.note ? 'How to read this and how it is measured' : 'How this is measured'}
            </summary>
            {data.note && <p className="mt-2">{data.note}</p>}
            {data.methodology?.length ? (
              <ol className="mt-2 list-decimal space-y-1 pl-5">
                {data.methodology.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            ) : null}
          </details>
        ) : null}
      </div>
    </div>
  );
  // The printed sheet: the same switches, controls and chart, drawn for paper.
  const explanation =
    data.note || data.methodology?.length ? (
      <>
        {data.note && (
          <p>
            <span className="font-medium text-foreground">How to read this. </span>
            {data.note}
          </p>
        )}
        {data.methodology?.length ? (
          <div>
            <p className="font-medium text-foreground">How it is measured</p>
            <ol className="list-decimal pl-4">
              {data.methodology.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          </div>
        ) : null}
      </>
    ) : undefined;
  const filters = (
    <>
      {/* A card's shared tab names the variant; a chart's own tabs print themselves. */}
      {!leading && period !== title && <PrintFilter label="View" value={period} />}
      {leading}
      {toolbar}
      {printFilters.map(
        (filter) =>
          filter && <PrintFilter key={filter.label} label={filter.label} value={filter.value} />,
      )}
      {focus && (
        <PrintFilter
          label="Focus"
          value={`${DIMENSION_LABELS[focus.dimension]} ${focus.value}${
            supported && focusFound ? '' : ' (not in this chart)'
          }`}
        />
      )}
    </>
  );

  return (
    <>
      {previewing && (
        <Suspense fallback={null}>
          <ChartPrintDialog
            open={previewing}
            onOpenChange={setPreviewing}
            onClosed={() => requestAnimationFrame(() => printRef.current?.focus())}
            aspect={printAspect}
            title={title}
            eyebrow={[org, section].filter(Boolean).join(' · ')}
            subtitle={detail}
            filters={filters}
            legend={controls}
            chart={(box) => chart(false, box)}
            notes={
              <>
                <p>{data.population}</p>
                <p>{windowNote}</p>
              </>
            }
            explanation={explanation}
          />
        </Suspense>
      )}
      {/* While printing, an expanded chart also prints in place. Its dialog keeps
          its own copy mounted (hidden by print.css), so the open explanation and
          scroll position are still there afterwards. */}
      {expanded && !printing ? (
        <div className="flex h-[340px] items-center justify-center text-sm text-muted-foreground">
          Chart opened in expanded view
        </div>
      ) : (
        content
      )}
      <Dialog open={expanded} onOpenChange={setExpanded}>
        <DialogContent
          className="max-h-[94dvh] overflow-y-auto sm:max-w-[min(96vw,1280px)]"
          aria-describedby={undefined}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            requestAnimationFrame(() => expandRef.current?.focus());
          }}
        >
          <DialogHeader>
            <DialogTitle>{heading}</DialogTitle>
          </DialogHeader>
          {expanded && content}
        </DialogContent>
      </Dialog>
    </>
  );
}

/** A scrollable data table with a sticky header, shared by every view. */
export const TABLE_CONTAINER = 'max-h-[440px] overflow-auto rounded-lg border';
