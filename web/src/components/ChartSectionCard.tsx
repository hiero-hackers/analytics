/**
 * One chart section as its own card, mirroring the legacy dashboard: a title
 * and description, then each chart as a figure with variant tabs (All /
 * Active…), optional slideshow navigation, horizontal scroll for wide charts,
 * and a lightbox that reveals the "how to read this" note and step-by-step
 * methodology. The PNGs carry their provenance footer in the image itself.
 */

import { useState } from "react";
import { chartUrl, fetchApiText, type ChartSection, type ChartSpec, type Manifest } from "../api";
import { downloadCsvText } from "../csv";
import { ChartLightbox, type LightboxContent } from "./ChartLightbox";
import { CopyLinkButton } from "./CopyLinkButton";

function Figure({
  chart,
  onZoom,
  slide = false,
  stretch = false,
}: {
  chart: ChartSpec;
  onZoom: (chart: ChartSpec, variant: number) => void;
  slide?: boolean;
  /** Span the full row even though the chart itself is half-width shaped. */
  stretch?: boolean;
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
}: {
  section: ChartSection;
  provenance: Manifest["provenance"];
}) {
  const [slide, setSlide] = useState(0);
  const [zoom, setZoom] = useState<LightboxContent | null>(null);

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
                    downloadCsvText(download.name, section.title, text, provenance, download.generated_at),
                  )
                }
              >
                Download CSV
              </button>
            )}
          </div>
        </div>
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
          <Figure key={section.charts[slide].title} chart={section.charts[slide]} onZoom={onZoom} slide />
        </div>
      ) : (
        <div className="gallery">
          {section.charts.map((chart, index) => (
            <Figure key={chart.title} chart={chart} onZoom={onZoom} stretch={stretched[index]} />
          ))}
        </div>
      )}
      {zoom && <ChartLightbox content={zoom} onClose={() => setZoom(null)} />}
    </section>
  );
}
