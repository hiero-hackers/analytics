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
  /** More height than its peers: rankings may show more rows before "Show all". */
  roomy?: boolean;
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
  // The unit leads the subtitle, without saying the same thing twice: the
  // variant label often repeats it ("Maintainers" beside a unit of
  // "Maintainers (share of repository)").
  const unit = data.unit.toLowerCase();
  const parts = subtitle.split(' · ').filter(Boolean);
  const detail = parts[0]?.toLowerCase().startsWith(unit)
    ? subtitle
    : [
        data.unit,
        ...(parts[0] && unit.startsWith(parts[0].toLowerCase()) ? parts.slice(1) : parts),
      ].join(' · ');
  // A snapshot already names its time; repeating it as "Source generated" adds a line and nothing else.
  const freshness = data.generated_at
    ? `Source generated ${stamp(data.generated_at)} UTC${data.stale ? ' · older than the scheduled refresh' : ''}`
    : 'Source freshness is unavailable.';
  const showFreshness =
    !data.generated_at || data.stale || !windowNote.includes(stamp(data.generated_at));

  const content = (
    // A container, so the toolbar can drop its labels in a narrow card.
    <div className="@container min-w-0 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
        <div className="min-w-0">
          {/* The dialog's own title already names the chart. */}
          {!expanded && <p className="text-sm font-semibold">{title}</p>}
          <p className="mt-1 text-xs text-muted-foreground">{detail}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <VariantTabs
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
        {/* The counting rule and the window stay visible; the reading guide
            folds away with the methodology, so a footer never outgrows its chart. */}
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
