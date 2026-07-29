/**
 * The macro's headline tiles.
 *
 * A tile is a single number with no axis and no rows behind it, so it is the
 * easiest figure here to misread. Each one is therefore clickable and opens
 * the same explanation panel a chart does — its "how to read this" note and
 * the steps that produced it.
 */

import { useState } from "react";
import type { MetricTile } from "../api";
import { ChartLightbox, type LightboxContent } from "./ChartLightbox";

export function MetricTiles({ tiles }: { tiles: MetricTile[] }) {
  const [explained, setExplained] = useState<LightboxContent | null>(null);

  if (tiles.length === 0) {
    return null;
  }
  return (
    <>
      <div className="mb-6 grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-3">
        {tiles.map((tile) => {
          const explainable = Boolean(tile.note || tile.methodology?.length);
          const body = (
            <>
              <div className="text-[13px] text-muted">{tile.label}</div>
              <div className="mt-0.5 text-[26px] font-semibold text-ink">{tile.value}</div>
            </>
          );
          const shell = "rounded-[10px] border border-solid border-edge bg-surface px-4 py-3.5 text-left";
          return explainable ? (
            <button
              key={tile.label}
              type="button"
              className={`${shell} cursor-pointer hover:border-[#999]`}
              title="How is this measured?"
              onClick={() =>
                setExplained({ alt: tile.label, title: tile.label, note: tile.note, methodology: tile.methodology })
              }
            >
              {body}
            </button>
          ) : (
            <div className={shell} key={tile.label}>
              {body}
            </div>
          );
        })}
      </div>
      {explained && <ChartLightbox content={explained} onClose={() => setExplained(null)} />}
    </>
  );
}
