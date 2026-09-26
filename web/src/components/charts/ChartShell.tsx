/**
 * The frame every interactive chart shares: heading, Chart / Data switch, CSV
 * download of the selected rows, the expanded dialog, and the explanatory
 * footer (note, counting rule, window, freshness, methodology).
 *
 * Views own their selection state (hidden series, search, the selected node)
 * and hand the shell the chart, the table and the CSV built from that one
 * selection, so the three can never disagree.
 */

import { useRef, useState, type ReactNode } from 'react';
import { CrosshairIcon } from 'lucide-react';
import { Maximize2Icon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import type { ChartDocumentMeta, Manifest } from '../../api';
import type { CsvExport } from '../../csv';
import { DIMENSION_LABELS, dimensionOf, useFocus } from '../../focus';
import { stamp } from '../../format';
import { useUrlIndex } from '../../urlState';
import { CsvDownloadButton } from '../CsvDownloadButton';
import { VariantTabs } from '../VariantTabs';

export interface ViewProps<T> {
  data: T;
  title: string;
  period: string;
  provenance: Manifest['provenance'];
}

export function ChartShell({
  data,
  title,
  period,
  provenance,
  subtitle,
  controls,
  chart,
  table,
  csv,
  windowNote,
  empty,
  emptyText = 'No data is available for this selection.',
  focusFound = true,
}: ViewProps<ChartDocumentMeta> & {
  subtitle: string;
  /** Above the chart and table alike: cohort tabs, series toggles, search. */
  controls?: ReactNode;
  chart: (expanded: boolean) => ReactNode;
  table: ReactNode;
  csv: () => Omit<CsvExport, 'total' | 'dataAsOf'>;
  windowNote: string;
  empty: boolean;
  emptyText?: string;
  /** Whether the focused value appears in this chart (when it has the dimension). */
  focusFound?: boolean;
}) {
  // Chart / Data lives in the URL, so a shared link opens the same view.
  const [view, setView] = useUrlIndex(`${data.id}.view`);
  const [focus, setFocus] = useFocus();
  const supported = focus ? data.dimensions.some((d) => dimensionOf(d) === focus.dimension) : false;
  const [expanded, setExpanded] = useState(false);
  const expandRef = useRef<HTMLButtonElement>(null);
  const heading = period !== title ? `${title} · ${period}` : title;

  const content = (
    <div className="min-w-0 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold">{data.unit}</p>
          <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <VariantTabs
            labels={['Chart', 'Data']}
            active={view}
            onSelect={setView}
            ariaLabel={`${title} display`}
          />
          <CsvDownloadButton
            provenance={provenance}
            payload={() => {
              const source = csv();
              return { ...source, total: source.rows.length, dataAsOf: data.generated_at };
            }}
          />
          {!expanded && (
            <Button
              ref={expandRef}
              variant="outline"
              size="sm"
              aria-label={`Expand interactive chart: ${title}`}
              onClick={() => setExpanded(true)}
            >
              <Maximize2Icon /> Expand
            </Button>
          )}
        </div>
      </div>
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
        {data.note && <p className="mb-2">{data.note}</p>}
        <p>{data.population}</p>
        <p className="mt-2">{windowNote}</p>
        <p className={data.stale ? 'mt-1 text-warn-ink' : 'mt-1'}>
          {data.generated_at
            ? `Source generated ${stamp(data.generated_at)} UTC${data.stale ? ' · older than the scheduled refresh' : ''}`
            : 'Source freshness is unavailable.'}
        </p>
        {data.methodology?.length ? (
          <details className="mt-3">
            <summary className="cursor-pointer font-medium text-foreground">
              How this is measured
            </summary>
            <ol className="mt-2 list-decimal space-y-1 pl-5">
              {data.methodology.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          </details>
        ) : null}
      </div>
    </div>
  );
  return (
    <>
      {expanded ? (
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
