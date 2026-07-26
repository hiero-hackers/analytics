/**
 * A generic entity x category coverage matrix (today: HIPs x components).
 *
 * Faithful to the legacy dashboard's matrix: banded column headers, a
 * governance column, heat-bucketed cells (the ramp ships with the view), a
 * trailing parity note, a text filter combined with a single-select status
 * pill, a legend, and a click-through evidence panel per filled cell. Row
 * order is the API's (hottest first) — the matrix is a heat map, not a
 * sortable table.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import type { MatrixRow, MatrixView } from "../api";
import type { EvidenceItem } from "./EvidencePanel";
import { EvidencePanel } from "./EvidencePanel";

/** The board's "show in matrix" request; nonce re-triggers repeat jumps. */
export interface JumpRequest {
  hip: number;
  nonce: number;
}

const FLASH_MS = 1800;

function cellClass(merged: number, open: number, ceilings: number[]): string {
  if (merged > 0) {
    const bucket = ceilings.findIndex((ceiling) => merged <= ceiling);
    return bucket === -1 ? `m${ceilings.length + 1}` : `m${bucket + 1}`;
  }
  return open > 0 ? "mo" : "m0";
}

/** Everything the legacy row matched its text filter against. */
function haystack(row: MatrixRow): string {
  const cells = row.cells.map((cell) => (cell.merged > 0 ? String(cell.merged) : cell.open > 0 ? "○" : "—"));
  return [row.label, row.sublabel, row.status, row.note.text, ...cells].join(" ").toLowerCase();
}

export function CoverageMatrix({
  view,
  evidence,
  jump,
}: {
  view: MatrixView;
  evidence: Map<string, EvidenceItem[]>;
  jump: JumpRequest | null;
}) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<{ hip: number; repo: string } | null>(null);
  const [flashHip, setFlashHip] = useState<number | null>(null);
  const tableRef = useRef<HTMLTableElement>(null);

  // A board jump clears any filter that would hide the target row, then
  // scrolls to it and flashes it — exactly the legacy behaviour.
  useEffect(() => {
    if (!jump) return;
    setQuery("");
    setStatus("");
    setSelected(null);
    setFlashHip(jump.hip);
    const row = tableRef.current?.querySelector(`#hipmx-row-${jump.hip}`);
    row?.scrollIntoView?.({ block: "center", behavior: "smooth" });
    const timer = setTimeout(() => setFlashHip(null), FLASH_MS);
    return () => clearTimeout(timer);
  }, [jump]);

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return view.rows.filter(
      (row) => (status === "" || row.status === status) && (needle === "" || haystack(row).includes(needle)),
    );
  }, [view.rows, query, status]);

  const selectedItems = selected ? evidence.get(`${selected.hip}|${selected.repo}`) : undefined;

  const toggleCell = (hip: number, repo: string) => {
    setSelected((current) => (current && current.hip === hip && current.repo === repo ? null : { hip, repo }));
  };

  return (
    <>
      <div className="hipmx-filters">
        <input
          className="search"
          placeholder="Filter by HIP number or title…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <div className="hipmx-fbar">
          <span>Governance:</span>
          {view.filters.map((option) => (
            <button
              key={option}
              type="button"
              className={option === status ? "hipmx-fbtn active" : "hipmx-fbtn"}
              onClick={() => setStatus((current) => (current === option ? "" : option))}
            >
              {option}
            </button>
          ))}
        </div>
      </div>
      <div className="hipmx-wrap">
        <table className="hipmx" ref={tableRef}>
          <thead>
            <tr className="hipmx-grp">
              <th />
              <th />
              {view.bands.map((band) => (
                <th key={band.label} colSpan={band.span}>
                  {band.label}
                </th>
              ))}
              <th />
            </tr>
            <tr>
              <th />
              <th className="hipmx-status-h">{view.row_header}</th>
              {view.columns.map((column) => (
                <th key={column.key}>{column.label}</th>
              ))}
              <th>{view.note_header}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key} id={`hipmx-row-${row.key}`} className={row.key === flashHip ? "flash" : undefined}>
                <th>
                  {row.label}
                  <small>{row.sublabel}</small>
                </th>
                <td className="hipmx-status">{row.status}</td>
                {row.cells.map((cell) => {
                  const clickable = evidence.has(`${row.key}|${cell.key}`);
                  const isSelected = selected?.hip === row.key && selected?.repo === cell.key;
                  if (cell.merged === 0 && cell.open === 0) {
                    return (
                      <td key={cell.key} className="m0" title="no PRs found">
                        —
                      </td>
                    );
                  }
                  const heat = cellClass(cell.merged, cell.open, view.ramp_ceilings);
                  return (
                    <td
                      key={cell.key}
                      className={`${heat} ck${isSelected ? " sel" : ""}`}
                      title={
                        cell.merged > 0
                          ? `${cell.merged} merged PRs — click for the list`
                          : `${cell.open} open PRs, none merged — click for the list`
                      }
                      {...(clickable && {
                        onClick: () => toggleCell(row.key, cell.key),
                        onKeyDown: (event: React.KeyboardEvent) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            toggleCell(row.key, cell.key);
                          }
                        },
                        tabIndex: 0,
                        role: "button",
                      })}
                    >
                      {cell.merged > 0 ? cell.merged : "○"}
                    </td>
                  );
                })}
                <td className="hipmx-gaps">
                  {row.note.kind === "complete" ? (
                    <span className="ok">{row.note.text}</span>
                  ) : row.note.kind === "none" ? (
                    <span className="none">{row.note.text}</span>
                  ) : (
                    row.note.text
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="hipmx-legend">
        fewer
        {view.ramp.map((shade) => (
          <i key={shade} style={{ background: shade }} />
        ))}
        more merged PRs&nbsp;&nbsp;·&nbsp;&nbsp;○ open PRs only&nbsp;&nbsp;·&nbsp;&nbsp;— no reference found
      </div>
      {selected && selectedItems && (
        <EvidencePanel
          hip={selected.hip}
          repo={selected.repo}
          items={selectedItems}
          onClose={() => setSelected(null)}
        />
      )}
      <p className="count">{rows.length} rows</p>
    </>
  );
}
