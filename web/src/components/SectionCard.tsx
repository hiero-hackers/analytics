/**
 * The chrome every content card shares: a collapsible header with a row/size
 * badge, then a body carrying the description, the freshness stamp, whatever
 * actions belong to the card, and the content itself.
 *
 * Tables and bespoke views both render through this, so a change to the header
 * (or the "data as of" treatment) cannot apply to one and miss the other.
 */

import type { ReactNode } from "react";
import { stamp } from "../format";

export function SectionCard({
  title,
  badge,
  description,
  generatedAt,
  stale,
  actions,
  children,
}: {
  title: string;
  badge: ReactNode;
  description: string;
  generatedAt?: string;
  stale?: boolean;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <details className="card tsec" open>
      <summary className="tsum">
        <h2>{title}</h2>
        <span className="sbadge">{badge}</span>
      </summary>
      <div className="sbody">
        <div className="shead">
          <p className="desc">{description}</p>
          {/* Right column: actions on top, freshness beneath — one place to
              look instead of three items jostling on a single line. */}
          <div className="sactions">
            {actions && <div className="actionrow">{actions}</div>}
            {generatedAt && (
              <span className={stale ? "asof stale" : "asof"}>
                data as of {stamp(generatedAt)}
                {stale ? " — older than the scheduled refresh" : ""}
              </span>
            )}
          </div>
        </div>
        {children}
      </div>
    </details>
  );
}
