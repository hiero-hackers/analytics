/**
 * A chart's "how to read this" note and step-by-step methodology, rendered
 * inside the lightbox caption: a `.chartnote` paragraph and a collapsible
 * `.lbmethod` details with an ordered list of steps. The content comes from
 * `CHART_NOTES` / `CHART_METHODOLOGY` in `dashboard_spec/`, shipped through
 * the data API.
 */

import { emphasized } from "../markup";

export interface ChartInfoProps {
  note?: string;
  methodology?: string[];
}

export function ChartInfo({ note, methodology }: ChartInfoProps) {
  if (!note && !methodology) {
    return null;
  }
  return (
    <>
      {note && <p className="chartnote">{emphasized(note)}</p>}
      {methodology && methodology.length > 0 && (
        <details className="lbmethod">
          <summary>Step-by-step methodology</summary>
          <ol>
            {methodology.map((step) => (
              <li key={step}>{emphasized(step)}</li>
            ))}
          </ol>
        </details>
      )}
    </>
  );
}
