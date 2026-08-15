/**
 * The contributor activity heatmap, rendered live from API data instead of a
 * matplotlib PNG (#333).
 *
 * Colour is interpolated continuously against the app's existing --heat-1
 * through --heat-5 CSS tokens (same ones the HIP coverage matrix uses), not
 * picked from a fixed bucket count: activity scores are unbounded and grow
 * with community activity, so a bucketed ramp would lose resolution over
 * time. Reading the tokens via getComputedStyle means dark mode is handled
 * for free — the browser already resolves the right value per the existing
 * prefers-color-scheme rule in app.css.
 */

import { useMemo } from "react";
import type { HeatmapView } from "../api";

const HEAT_TOKENS = ["--heat-1", "--heat-2", "--heat-3", "--heat-4", "--heat-5"] as const;

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.trim().replace("#", "");
  const value = parseInt(clean, 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function rgbToCss([r, g, b]: [number, number, number]): string {
  return `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`;
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

/** Read the five heat stops as resolved colours for the current theme. */
function readHeatStops(): [number, number, number][] {
  const styles = getComputedStyle(document.documentElement);
  return HEAT_TOKENS.map((token) => hexToRgb(styles.getPropertyValue(token) || "#cccccc"));
}

function heatRatio(value: number, max: number): number {
  if (max <= 0) return 0;
  return Math.min(Math.max(value / max, 0), 1);
}

/**
 * Map a value in [0, max] to a colour continuously interpolated across the
 * five heat stops — not a bucket lookup. A value of 0 always renders as the
 * lightest stop; max_value (or above) renders as the darkest.
 */
function interpolateHeat(ratio: number, stops: [number, number, number][]): string {
  const scaled = ratio * (stops.length - 1);
  const lowerIndex = Math.floor(scaled);
  const upperIndex = Math.min(lowerIndex + 1, stops.length - 1);
  const t = scaled - lowerIndex;
  const lower = stops[lowerIndex];
  const upper = stops[upperIndex];
  return rgbToCss([lerp(lower[0], upper[0], t), lerp(lower[1], upper[1], t), lerp(lower[2], upper[2], t)]);
}

export function ActivityHeatmap({ view }: { view: HeatmapView }) {
  const stops = useMemo(() => readHeatStops(), []);

  if (view.rows.length === 0 || view.columns.length === 0) {
    return <p className="empty-state">No activity in the current window.</p>;
  }

  return (
    <div className="activity-heatmap">
      <table aria-label={view.title}>
        <thead>
          <tr>
            <th scope="col">Contributor</th>
            {view.columns.map((column) => (
              <th scope="col" key={column}>
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {view.rows.map((rowLabel, rowIndex) => (
            <tr key={rowLabel}>
              <th scope="row">{rowLabel}</th>
              {view.values[rowIndex].map((value, columnIndex) => {
                const ratio = heatRatio(value, view.max_value);
                return (
                  <td
                    key={view.columns[columnIndex]}
                    style={{ backgroundColor: interpolateHeat(ratio, stops) }}
                    // Exposes the deterministic 0..1 position independent of
                    // any CSS actually being loaded (this project's tests run
                    // with css: false), so correctness is checkable without
                    // depending on jsdom resolving custom properties.
                    data-ratio={ratio.toFixed(3)}
                    title={`${rowLabel}, ${view.columns[columnIndex]}: ${value}`}
                  >
                    <span className="sr-only">{value}</span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
