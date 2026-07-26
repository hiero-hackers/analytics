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

function Figure({
  chart,
  onZoom,
  slide = false,
}: {
  chart: ChartSpec;
  onZoom: (chart: ChartSpec, variant: number) => void;
  slide?: boolean;
}) {
  const [variant, setVariant] = useState(0);
  const active = chart.variants[Math.min(variant, chart.variants.length - 1)];
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
    <figure className={slide ? "slide" : chart.wide ? "chart wide" : "chart"}>
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
          <Figure key={section.charts[slide].title} chart={section.charts[slide]} onZoom={onZoom} slide />
        </div>
      ) : (
        <div className="gallery">
          {section.charts.map((chart) => (
            <Figure key={chart.title} chart={chart} onZoom={onZoom} />
          ))}
        </div>
      )}
      {zoom && <ChartLightbox content={zoom} onClose={() => setZoom(null)} />}
    </section>
  );
}
