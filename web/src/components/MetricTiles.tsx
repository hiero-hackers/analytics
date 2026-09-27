/**
 * The tab's headline figures as stat tiles.
 *
 * A figure is a single number with no axis and no rows behind it, so it is the
 * easiest thing here to misread. Each tile therefore says what kind of number
 * it is: a count reads as a plain figure, a share ("72%") or a part of a whole
 * ("26 of 44") also draws a meter on a same-hue track, so the proportion reads
 * at a glance and two shares compare without mental arithmetic. A tile with
 * an explanation is a button that opens its "how to read this" note and the
 * steps that produced it, and says so with an info mark.
 *
 * The label comes first in the DOM, so a tile is announced as "maintainers
 * 103"; capitalisation is visual only (`first-letter`), which keeps that
 * accessible name exactly the label the pipeline wrote.
 */

import { useState } from 'react';
import { InfoIcon } from 'lucide-react';
import { cn } from 'cn';
import type { MetricTile } from '../api';
import { readFigure, type Figure } from '../metricFigure';
import { ExplanationDialog, type Explanation } from './ExplanationDialog';

/** "open PRs %" beside "72%" says the unit twice; the figure keeps it. */
const labelFor = (label: string, figure: Figure) =>
  figure.kind === 'share' ? label.replace(/\s*%$/, '') : label;

function Value({ figure }: { figure: Figure }) {
  return (
    // Proportional figures: tabular digits look loose at display size.
    <div className="flex items-baseline gap-0.5 text-[2.25rem] leading-none font-semibold tracking-tight text-foreground">
      {figure.value}
      {figure.kind === 'share' && (
        <span className="text-xl font-medium text-muted-foreground">%</span>
      )}
      {figure.kind === 'part' && (
        <span className="ml-1 text-sm font-medium tracking-normal text-muted-foreground">
          {' '}
          of {figure.of}
        </span>
      )}
    </div>
  );
}

function Meter({ percent }: { percent: number }) {
  return (
    <div aria-hidden="true" className="h-1.5 w-full overflow-hidden rounded-full bg-raise">
      <div
        className="h-full rounded-full bg-link transition-[width] duration-500 motion-reduce:transition-none"
        style={{ width: `${Math.max(percent, percent > 0 ? 2 : 0)}%` }}
      />
    </div>
  );
}

const TILE =
  'group/figure relative flex min-w-0 flex-col justify-between gap-4 rounded-xl border bg-card p-4 text-left shadow-xs';

export function MetricTiles({ tiles }: { tiles: MetricTile[] }) {
  const [explained, setExplained] = useState<Explanation | null>(null);

  if (tiles.length === 0) {
    return null;
  }
  return (
    <section aria-label="Headline figures" className="mb-8">
      <div className="grid grid-cols-2 gap-3 min-[600px]:grid-cols-3 lg:grid-cols-[repeat(auto-fit,minmax(9rem,1fr))]">
        {tiles.map((tile, index) => {
          const figure = readFigure(tile.value);
          const explainable = Boolean(tile.note || tile.methodology?.length);
          const body = (
            <>
              <div className="flex items-start justify-between gap-2">
                <span className="text-xs leading-snug font-medium text-muted-foreground first-letter:uppercase">
                  {labelFor(tile.label, figure)}
                </span>
                {explainable && (
                  <InfoIcon
                    aria-hidden="true"
                    className="mt-px size-3.5 shrink-0 text-muted-foreground/70 transition-colors group-hover/figure:text-link"
                  />
                )}
              </div>
              <div className="space-y-2.5">
                <Value figure={figure} />
                {figure.kind === 'share' || figure.kind === 'part' ? (
                  <Meter percent={figure.percent} />
                ) : (
                  // The meter's room, kept empty, so every number in a row sits on one line.
                  <div aria-hidden="true" className="h-1.5" />
                )}
              </div>
            </>
          );
          // Two columns on a phone: an odd number of tiles lets the first span
          // the row instead of leaving the last one alone.
          const span = tiles.length % 2 === 1 && index === 0 && 'max-[599px]:col-span-2';
          return explainable ? (
            <button
              key={tile.label}
              type="button"
              title="How is this measured?"
              className={cn(
                TILE,
                span,
                'cursor-pointer outline-none transition-[border-color,box-shadow] hover:border-link/40 hover:shadow-sm focus-visible:ring-2 focus-visible:ring-ring',
              )}
              onClick={() =>
                setExplained({ title: tile.label, note: tile.note, methodology: tile.methodology })
              }
            >
              {body}
            </button>
          ) : (
            <div key={tile.label} className={cn(TILE, span)}>
              {body}
            </div>
          );
        })}
      </div>
      {explained && <ExplanationDialog content={explained} onClose={() => setExplained(null)} />}
    </section>
  );
}
