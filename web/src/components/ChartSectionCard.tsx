/**
 * Chart section cards. Charts offering the same variant labels share one card-level
 * tab row; every selection lives in the URL.
 */

import { lazy, Suspense } from 'react';
import { parseIndex, useUrlIndex, useUrlList } from '../urlState';
import { ChevronLeftIcon, ChevronRightIcon } from 'lucide-react';
import { cn } from 'cn';
import { Button } from '@/components/ui/button';
import { fetchApiText, type ChartSection, type ChartSpec, type Manifest } from '../api';
import { downloadCsvText } from '../csv';
import { usePrintMode } from '../printContext';
import { CopyLinkButton } from './CopyLinkButton';
import { DownloadButton } from './CsvDownloadButton';
import { SectionCard } from './SectionCard';
import { VariantTabs } from './VariantTabs';

const InteractiveChart = lazy(() => import('./InteractiveChart'));

/** Hand-flagged charts and wide kinds (heatmaps, networks, timelines) take a full row. */
const WIDE_KINDS = ['matrix', 'network', 'events'];
const needsFullRow = (chart: ChartSpec, variant: number) =>
  Boolean(
    chart.wide ||
    chart.full_row ||
    WIDE_KINDS.includes(chart.variants[variant]?.interactive?.kind ?? ''),
  );

/** A chart's variant axis: its ordered label set, serialised so no separator can clash. */
const axisOf = (chart: ChartSpec) => JSON.stringify(chart.variants.map((variant) => variant.label));

function Figure({
  chart,
  stateKey,
  slide = false,
  stretch = false,
  lead = false,
  axis,
  provenance,
  hidden = false,
}: {
  chart: ChartSpec;
  /** URL key for this figure's own tab, so a shared link opens the same variant. */
  stateKey: string;
  provenance: Manifest['provenance'];
  slide?: boolean;
  /** Span the full row even though the chart itself is half-width shaped. */
  stretch?: boolean;
  /** The gallery's lead chart: two rows tall, with the shorter charts stacked beside it. */
  lead?: boolean;
  /** Set when the card owns this chart's axis: it renders one tab row for all
   *  the charts that share it, so this figure shows none of its own. */
  axis?: { index: number; onSelect: (index: number) => void };
  /** A slideshow's off-screen slide: mounted, so its variant and loaded data survive. */
  hidden?: boolean;
}) {
  const [own, setOwn] = useUrlIndex(stateKey);
  const variant = Math.min(axis ? axis.index : own, chart.variants.length - 1);
  const active = chart.variants[variant];
  const fullRow = stretch || needsFullRow(chart, variant);
  return (
    <figure
      hidden={hidden}
      aria-label={`${chart.title} — ${active.label}`}
      className={cn(
        'm-0 min-w-0 rounded-xl border bg-background/40 p-3',
        (slide || fullRow) && 'col-span-full',
        lead && !fullRow && 'lg:row-span-2',
      )}
    >
      {/* Interactive charts render their tabs in their own toolbar. */}
      {!axis && !active.interactive && (
        <VariantTabs
          labels={chart.variants.map((option) => option.label)}
          active={variant}
          onSelect={setOwn}
          ariaLabel={`${chart.title} view`}
        />
      )}
      {active.interactive ? (
        <Suspense
          fallback={
            <p role="status" data-print-pending className="p-10 text-center text-muted-foreground">
              Loading chart: {chart.title} ({active.label})…
            </p>
          }
        >
          <InteractiveChart
            key={active.interactive.path}
            variant={active}
            title={chart.title}
            provenance={provenance}
            roomy={lead}
            leading={
              axis ? undefined : (
                <VariantTabs
                  appearance="segmented"
                  labels={chart.variants.map((option) => option.label)}
                  active={variant}
                  onSelect={setOwn}
                  ariaLabel={`${chart.title} view`}
                />
              )
            }
          />
        </Suspense>
      ) : (
        <div
          role="status"
          className="flex min-h-48 flex-col justify-center gap-2 rounded-lg border border-dashed p-6 text-sm"
        >
          <p className="font-medium">Chart data is not available yet</p>
          <p className="text-muted-foreground">
            This view will appear when its source dataset is published in the next analytics
            refresh.
          </p>
          <details className="text-muted-foreground">
            <summary className="cursor-pointer">About this chart</summary>
            <p className="mt-2">{active.note ?? chart.note}</p>
            <ol className="mt-2 list-inside list-decimal">
              {(active.methodology ?? chart.methodology ?? []).map((step, index) => (
                <li key={index}>{step}</li>
              ))}
            </ol>
          </details>
        </div>
      )}
      {/* An interactive chart names itself in its header; the placeholder does not. */}
      {!active.interactive && (
        <figcaption
          className={cn(
            'mt-3 text-left text-xs font-medium text-foreground',
            slide && 'text-sm font-semibold',
          )}
        >
          {chart.title}
        </figcaption>
      )}
    </figure>
  );
}

export function ChartSectionCard({
  section,
  provenance,
}: {
  section: ChartSection;
  provenance: Manifest['provenance'];
}) {
  const printing = usePrintMode();
  // In the URL so Copy link reproduces the view; shared axes as `<section>.tab=<i>,<j>`.
  const [rawSlide, setSlide] = useUrlIndex(`${section.id}.slide`);
  const [rawShared, setRawShared] = useUrlList(`${section.id}.tab`);

  const count = section.charts.length;
  const slide = Math.min(rawSlide, count - 1);

  // An axis belongs to the card once two charts offer the same labels; a lone
  // multi-variant chart keeps its own tabs where they sit, under its caption.
  const axisCounts = new Map<string, number>();
  for (const chart of section.charts) {
    if (chart.variants.length > 1) {
      const axis = axisOf(chart);
      axisCounts.set(axis, (axisCounts.get(axis) ?? 0) + 1);
    }
  }
  const sharedAxes = section.charts
    .filter((chart) => chart.variants.length > 1 && (axisCounts.get(axisOf(chart)) ?? 0) > 1)
    .map((chart) => ({ key: axisOf(chart), labels: chart.variants.map((v) => v.label) }))
    .filter((axis, index, all) => all.findIndex((other) => other.key === axis.key) === index);
  const shared: Record<string, number> = Object.fromEntries(
    sharedAxes.map((axis, i) => [
      axis.key,
      Math.min(parseIndex(rawShared[i]), axis.labels.length - 1),
    ]),
  );
  const setShared = (next: Record<string, number>) =>
    setRawShared(
      sharedAxes.every((axis) => !next[axis.key])
        ? []
        : sharedAxes.map((axis) => String(next[axis.key] ?? 0)),
    );
  const axisFor = (chart: ChartSpec) =>
    sharedAxes.some((axis) => axis.key === axisOf(chart))
      ? {
          index: shared[axisOf(chart)] ?? 0,
          onSelect: (index: number) => setShared({ ...shared, [axisOf(chart)]: index }),
        }
      : undefined;

  // The gallery lays half-width charts out in pairs; full-row charts break the
  // pairing. A half-width chart stretches to the full row only when it is the
  // *only* half-width chart in the gallery (every sibling is full-row, so it
  // could never have a partner). With two or more half-width siblings they all
  // stay half — a trailing odd one out at half width reads better than one
  // chart rendering huge next to its same-shaped siblings. Variant 0's shape
  // decides, keeping the grid stable while variant tabs switch.
  const halfCount = section.charts.filter((chart) => !needsFullRow(chart, 0)).length;
  const stretched = section.charts.map((chart) => needsFullRow(chart, 0) || halfCount === 1);
  // An odd count (3+) of half-width charts would strand the last one, so the
  // first (usually the tallest) spans two rows and the others stack beside it.
  const leadIndex =
    halfCount >= 3 && halfCount % 2 === 1
      ? section.charts.findIndex((chart) => !needsFullRow(chart, 0))
      : -1;

  // A card whose tabs show different populations declares a companion CSV per
  // tab; offering one for the whole card would hand a reader on the Committers
  // tab the maintainer table. No entry for the active tab means no button.
  const activeLabel = sharedAxes.length
    ? sharedAxes[0].labels[shared[sharedAxes[0].key] ?? 0]
    : undefined;
  const download = section.downloads
    ? activeLabel
      ? section.downloads[activeLabel]
      : undefined
    : section.download;
  return (
    <SectionCard
      id={section.id}
      title={section.title}
      description={section.description}
      headerActions={<CopyLinkButton sectionId={section.id} quiet />}
      actions={
        download && (
          <DownloadButton
            onClick={() =>
              // The chart's companion table, stamped with the provenance
              // preamble like every other browser download.
              fetchApiText(download.path).then((text) =>
                downloadCsvText(
                  download.name,
                  section.title,
                  text,
                  provenance,
                  download.generated_at,
                ),
              )
            }
          />
        )
      }
    >
      {/* One row per shared axis, above the gallery: the card's charts switch
          together, so the control belongs to the card and not to each figure. */}
      {sharedAxes.map((axis) => (
        <VariantTabs
          key={axis.key}
          labels={axis.labels}
          active={shared[axis.key] ?? 0}
          onSelect={(index) => setShared({ ...shared, [axis.key]: index })}
          ariaLabel={`${section.title} view`}
        />
      ))}
      {section.slideshow && count > 1 ? (
        <div>
          <div className="mb-2.5 flex items-center gap-3" data-print-hide>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setSlide((slide - 1 + count) % count)}
            >
              <ChevronLeftIcon data-icon="inline-start" />
              Prev
            </Button>
            <span className="text-xs text-muted-foreground tabular-nums">
              {slide + 1} / {count}
            </span>
            <Button variant="outline" size="sm" onClick={() => setSlide((slide + 1) % count)}>
              Next
              <ChevronRightIcon data-icon="inline-end" />
            </Button>
          </div>
          {/* Every slide stays mounted, so each keeps its chosen variant across
              slide changes and print; paper prints them all, in order. */}
          {section.charts.map((chart, index) => (
            <Figure
              key={chart.title}
              chart={chart}
              stateKey={`${section.id}.${index}.tab`}
              provenance={provenance}
              slide
              axis={axisFor(chart)}
              hidden={!printing && index !== slide}
            />
          ))}
        </div>
      ) : (
        // Two columns at most for legibility; items-start stops a short chart
        // stretching beside a tall neighbour.
        <div className="grid grid-flow-row-dense grid-cols-1 items-start gap-4 lg:grid-cols-2">
          {section.charts.map((chart, index) => (
            <Figure
              key={chart.title}
              chart={chart}
              stateKey={`${section.id}.${index}.tab`}
              provenance={provenance}
              stretch={stretched[index]}
              lead={index === leadIndex}
              axis={axisFor(chart)}
            />
          ))}
        </div>
      )}
    </SectionCard>
  );
}
