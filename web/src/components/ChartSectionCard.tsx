/**
 * One chart section as its own card, mirroring the legacy dashboard: a title
 * and description, then each chart as a figure with variant tabs (All /
 * Active…), optional slideshow navigation, horizontal scroll for wide charts,
 * and a lightbox that reveals the "how to read this" note and step-by-step
 * methodology. The PNGs carry their provenance footer in the image itself.
 *
 * Charts that offer the *same* set of variant labels share one axis, owned by
 * the card: the Organisation-diversity card has three Maintainers/Committers
 * charts, and per-figure tabs let a reader end up comparing a maintainer donut
 * with a committer repo mix while the description promised the tabs switch the
 * view. Charts with any other label set (the period-tabbed cards elsewhere)
 * keep their own tabs, so nothing else changes.
 */

import { useState } from 'react';
import { chartUrl, fetchApiText, type ChartSection, type ChartSpec, type Manifest } from '../api';
import { downloadCsvText } from '../csv';
import { ChartLightbox, type LightboxContent } from './ChartLightbox';
import { CopyLinkButton } from './CopyLinkButton';
import { VariantTabs } from './VariantTabs';

/**
 * A chart's variant axis, identified by its ordered label set. Serialised
 * rather than joined so no separator can be confused with a label.
 */
const axisOf = (chart: ChartSpec) => JSON.stringify(chart.variants.map((variant) => variant.label));

function Figure({
  chart,
  onZoom,
  slide = false,
  stretch = false,
  liveView,
  axis,
}: {
  chart: ChartSpec;
  onZoom: (chart: ChartSpec, variant: number) => void;
  slide?: boolean;
  /** Span the full row even though the chart itself is half-width shaped. */
  stretch?: boolean;
  /** The fetched view this slide prefers, if chart.live_view_id matched one
   *  that loaded successfully. Falls back to the PNG variants below when
   *  absent — still loading, failed to fetch, or not produced for this org. */
  liveView?: HeatmapView;
  /** Set when the card owns this chart's axis: it renders one tab row for all
   *  the charts that share it, so this figure shows none of its own. */
  axis?: { index: number; onSelect: (index: number) => void };
}) {
  const [own, setOwn] = useState(0);
  const variant = Math.min(axis ? axis.index : own, chart.variants.length - 1);
  const active = chart.variants[variant];
  // A tall/square chart (a heatmap) in a ~340px gallery cell is illegible, but
  // the `wide` scroll-box treatment would shrink it to the box height instead.
  // It gets the full row with natural page flow: the dimensions ship with the
  // variant, so the shape decides — nobody hand-flags heatmaps.
  const tall = Boolean(active.width && active.height && active.width / active.height <= 1.05);
  // Full row without the scroll box: wide-aspect charts with few bars scale to
  // fit; only hand-flagged `wide` charts (many bars) get horizontal scrolling.
  const fullRow = chart.wide || chart.full_row || tall || stretch;

  if (chart.live_view_id && liveView) {
    // Live slides render inline where the PNG would've gone — no variant
    // tabs (there's one dataset, not several PNG files to switch between)
    // and no zoom-to-lightbox (the live grid is already legible in place).
    // `active` (the PNG variant) is guaranteed to exist here: this slide only
    // ever gets a live_view_id attached when its PNG variant survived
    // _org_chart_sections' existence filter, so linking to it is never a 404
    // — unlike view.png_fallback, which can genuinely be absent and is why
    // it isn't used here.
    return (
      <figure className={slide ? "slide" : "chart wide"}>
        <ActivityHeatmap view={liveView} />
        <figcaption>
          {chart.title} · <a href={chartUrl(active.file)} target="_blank" rel="noreferrer">View as static image</a>
        </figcaption>
      </figure>
    );
  }

  const img = (
    <img
      src={chartUrl(active.file)}
      alt={chart.title}
      loading="lazy"
      // Intrinsic size (when known) reserves the aspect-ratio box up front, so
      // a screen of lazy-loading charts doesn't shove content around as each
      // one arrives. CSS still controls the displayed width.
      width={active.width}
      height={active.height}
      onClick={() => onZoom(chart, variant)}
    />
  );
  return (
    <figure className={slide ? 'slide' : fullRow ? 'chart wide' : 'chart'}>
      {!axis && (
        <VariantTabs
          labels={chart.variants.map((option) => option.label)}
          active={variant}
          onSelect={setOwn}
          ariaLabel={`${chart.title} view`}
        />
      )}
      {chart.wide ? <div className="chartscroll">{img}</div> : img}
      <figcaption>{chart.title}</figcaption>
    </figure>
  );
}

export function ChartSectionCard({
  section,
  provenance,
  views = [],
}: {
  section: ChartSection;
  provenance: Manifest['provenance'];
}) {
  const [slide, setSlide] = useState(0);
  const [zoom, setZoom] = useState<LightboxContent | null>(null);
  const viewById = new Map(views.map((view) => [view.id, view]));
  // Only heatmap-kind views can currently be a live slide's target — this
  // narrows the lookup's return type without assuming every kind qualifies
  // as future kinds are added to ViewDoc.
  const liveViewFor = (chart: ChartSpec): HeatmapView | undefined => {
    if (!chart.live_view_id) return undefined;
    const view = viewById.get(chart.live_view_id);
    return view?.kind === "heatmap" ? view : undefined;
  };
  // One selection per shared axis, keyed by its label set.
  const [shared, setShared] = useState<Record<string, number>>({});

  const onZoom = (chart: ChartSpec, variant: number) =>
    setZoom({
      src: chartUrl(chart.variants[variant].file),
      alt: chart.title,
      // The tab's own text where it has one: on a role-tabbed chart the
      // chart-level note describes maintainers, and showing it on the
      // Committers tab misdescribes the population the reader is looking at.
      note: chart.variants[variant].note ?? chart.note,
      methodology: chart.variants[variant].methodology ?? chart.methodology,
    });
  const count = section.charts.length;

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
  const isFullRow = (chart: ChartSpec) => {
    const first = chart.variants[0];
    const tall = Boolean(first.width && first.height && first.width / first.height <= 1.05);
    return Boolean(chart.wide || chart.full_row || tall);
  };
  const halfCount = section.charts.filter((chart) => !isFullRow(chart)).length;
  const stretched = section.charts.map((chart) => isFullRow(chart) || halfCount === 1);

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
    <section className="card" id={section.id}>
      <h2>{section.title}</h2>
      <div className="shead">
        <p className="desc">{section.description}</p>
        <div className="sactions">
          <div className="actionrow">
            <CopyLinkButton sectionId={section.id} />
            {download && (
              <button
                className="dl"
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
              >
                Download CSV
              </button>
            )}
          </div>
        </div>
      </div>
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
        <div className="slideshow">
          <div className="slidenav">
            <button className="snav" onClick={() => setSlide((slide - 1 + count) % count)}>
              ‹ Prev
            </button>
            <span className="scount">
              {slide + 1} / {count}
            </span>
            <button className="snav" onClick={() => setSlide((slide + 1) % count)}>
              Next ›
            </button>
          </div>
          <Figure
            key={section.charts[slide].title}
            chart={section.charts[slide]}
            onZoom={onZoom}
            slide
            axis={axisFor(section.charts[slide])}
          />
        </div>
      ) : (
        <div className="gallery">
          {section.charts.map((chart, index) => (
            <Figure
              key={chart.title}
              chart={chart}
              onZoom={onZoom}
              stretch={stretched[index]}
              liveView={liveViewFor(chart)}
              axis={axisFor(chart)}
            />
          ))}
        </div>
      )}
      {zoom && <ChartLightbox content={zoom} onClose={() => setZoom(null)} />}
    </section>
  );
}
