/**
 * The tab's headline figures in responsive cards with aligned numerals.
 *
 * A figure is a single number with no axis and no rows behind it, so it is the
 * easiest thing here to misread. Each one with an explanation is therefore a
 * button that opens the same dialog a chart does — its "how to read this" note
 * and the steps that produced it — and says so with an info mark.
 *
 * The label comes first in the DOM (the number is shown above it by
 * flex-col-reverse), so a figure is announced as "maintainers 103"; both are
 * block elements so the accessible name keeps its space.
 */

import { useState } from 'react';
import { InfoIcon } from 'lucide-react';
import type { MetricTile } from '../api';
import { ChartLightbox, type LightboxContent } from './ChartLightbox';

// flex-col-reverse shows the number above its (DOM-first) label; justify-end
// packs from the top in a reversed column, so every number sits on one line
// even when a neighbour's label wraps to two.
const FIGURE =
  'flex min-w-0 flex-col-reverse justify-end gap-3 rounded-xl border bg-card p-5 text-left shadow-xs transition-colors hover:border-link/40';
const VALUE =
  'text-[2.5rem] leading-none font-semibold tracking-tight text-foreground tabular-nums';
const LABEL = 'text-xs font-medium leading-snug text-muted-foreground';

export function MetricTiles({ tiles }: { tiles: MetricTile[] }) {
  const [explained, setExplained] = useState<LightboxContent | null>(null);

  if (tiles.length === 0) {
    return null;
  }
  return (
    <section aria-label="Headline figures" className="mb-8">
      <div className="grid grid-cols-2 gap-3 min-[600px]:grid-cols-3 lg:grid-cols-[repeat(auto-fit,minmax(8.5rem,1fr))]">
        {tiles.map((tile) => {
          const explainable = Boolean(tile.note || tile.methodology?.length);
          return explainable ? (
            <button
              key={tile.label}
              type="button"
              title="How is this measured?"
              className={`${FIGURE} group/figure cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-ring`}
              onClick={() =>
                setExplained({
                  alt: tile.label,
                  title: tile.label,
                  note: tile.note,
                  methodology: tile.methodology,
                })
              }
            >
              <div className={LABEL}>
                <span className="underline decoration-dotted underline-offset-3 group-hover/figure:decoration-solid">
                  {tile.label}
                </span>
                {/* Inline, so it follows the label's last word when it wraps. */}
                <InfoIcon aria-hidden="true" className="ml-1 inline size-3 align-[-1px]" />
              </div>
              <div className={VALUE}>{tile.value}</div>
            </button>
          ) : (
            <div key={tile.label} className={FIGURE}>
              <div className={LABEL}>{tile.label}</div>
              <div className={VALUE}>{tile.value}</div>
            </div>
          );
        })}
      </div>
      {explained && <ChartLightbox content={explained} onClose={() => setExplained(null)} />}
    </section>
  );
}
