/**
 * One chart section as its own card, mirroring the legacy dashboard: a title
 * and description, then each chart as a figure with variant tabs (All /
 * Active…), optional slideshow navigation, horizontal scroll for wide charts,
 * and a lightbox that reveals the "how to read this" note and step-by-step
 * methodology. The PNGs carry their provenance footer in the image itself.
 */

import { useState } from "react";
import { chartUrl, fetchApiText, type ChartSection, type ChartSpec, type HeatmapView, type Manifest, type ViewDoc } from "../api";
import { downloadCsvText } from "../csv";
import { ActivityHeatmap } from "./ActivityHeatmap";
import { ChartLightbox, type LightboxContent } from "./ChartLightbox";

function Figure({
  chart,
  onZoom,
  slide = false,
  stretch = false,
  liveView,
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
}) {
  const [variant, setVariant] = useState(0);
  const active = chart.variants[Math.min(variant, chart.variants.length - 1)];
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
    <figure className={slide ? "slide" : fullRow ? "chart wide" : "chart"}>
      {chart.variants.length > 1 && (
        <div className="charttabs">
          {chart.variants.map((option, index) => (
            <button
              key={option.label}
              className={index === variant ? "ctab active" : "ctab"}
              onClick={() => setVariant(index)}
            >
              {option.label}
            </button>
          ))}
        </div>
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
  provenance: Manifest["provenance"];
  /** All of this org's fetched views (any kind) — used to resolve a slide's
   *  live_view_id, if it has one and that view loaded. Not the group-scoped,
   *  already-filtered list ViewCards renders; the raw fetched set, so a slide
   *  can find its view even when ViewCards has excluded it to avoid the
   *  duplicate render. Optional/defaulted so existing callers compile as-is. */
  views?: ViewDoc[];
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

  const onZoom = (chart: ChartSpec, variant: number) =>
    setZoom({
      src: chartUrl(chart.variants[variant].file),
      alt: chart.title,
      note: chart.note,
      methodology: chart.methodology,
    });
  const count = section.charts.length;

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

  const download = section.download;
  return (
    <section className="card">
      <h2>{section.title}</h2>
      <div className="shead">
        <p className="desc">{section.description}</p>
        {download && (
          <button
            className="dl"
            onClick={() =>
              // The chart's companion table, stamped with the provenance
              // preamble like every other browser download.
              fetchApiText(download.path).then((text) =>
                downloadCsvText(download.name, section.title, text, provenance, download.generated_at),
              )
            }
          >
            Download CSV
          </button>
        )}
      </div>
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
            liveView={liveViewFor(section.charts[slide])}
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
            />
          ))}
        </div>
      )}
      {zoom && <ChartLightbox content={zoom} onClose={() => setZoom(null)} />}
    </section>
  );
}
