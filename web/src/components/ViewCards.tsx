/**
 * A macro's bespoke views, rendered with the shared section chrome and
 * coordinated: the board's "show in coverage matrix" jump reaches the matrix,
 * and the matrix derives its per-cell evidence from the macro's evidence
 * section — same rows the evidence table shows, no duplicated payload.
 */

import { useMemo, useRef, useState } from "react";
import type { BoardView, Manifest, MatrixView, Row, SectionDoc, ViewDoc } from "../api";
import { CoverageMatrix, type JumpRequest } from "./CoverageMatrix";
import { type CsvExportSource } from "../csv";
import { CopyLinkButton } from "./CopyLinkButton";
import { CsvDownloadButton } from "./CsvDownloadButton";
import type { EvidenceItem } from "./EvidencePanel";
import { SectionCard } from "./SectionCard";
import { StatusBoard } from "./StatusBoard";

/** Per-cell evidence keyed "<entity>|<repo>", newest merged first. */
function evidenceByCell(rows: Row[]): Map<string, EvidenceItem[]> {
  const cells = new Map<string, EvidenceItem[]>();
  for (const row of rows) {
    const key = `${row.hip}|${row.repo}`;
    const items = cells.get(key) ?? [];
    items.push({
      n: Number(row.pr_number),
      t: String(row.pr_title ?? "").slice(0, 100),
      st: String(row.pr_state ?? ""),
      d: row.pr_merged_at ? String(row.pr_merged_at).slice(0, 10) : "",
      m: String(row.match_sources ?? ""),
      q: row.qualifier ? String(row.qualifier) : "",
      x: row.snippet ? String(row.snippet).slice(0, 90) : "",
    });
    cells.set(key, items);
  }
  for (const items of cells.values()) {
    items.sort((a, b) => b.d.localeCompare(a.d));
  }
  return cells;
}

/** The matrix as the reader sees it — wide format, one column per component. */
function matrixExport(view: MatrixView): CsvExportSource {
  const sdkColumns = view.columns.filter((column) => column.band === "SDKs");
  return {
    name: "hip_coverage_matrix",
    title: view.title,
    columns: [
      { key: "hip", label: "hip" },
      { key: "title", label: "title" },
      { key: "status", label: "status" },
      ...view.columns.map((column) => ({ key: column.key, label: column.label })),
      { key: "gaps", label: "no_merged_sdk_prs_in" },
    ],
    rows: view.rows.map((row) => {
      const byKey = new Map(row.cells.map((cell) => [cell.key, cell]));
      const record: Row = { hip: row.key, title: row.sublabel, status: row.status };
      for (const column of view.columns) {
        const cell = byKey.get(column.key);
        record[column.key] = !cell || cell.merged === 0 ? (cell && cell.open > 0 ? `open:${cell.open}` : 0) : cell.merged;
      }
      record.gaps = sdkColumns
        .filter((column) => (byKey.get(column.key)?.merged ?? 0) === 0)
        .map((column) => column.label)
        .join(" | ");
      return record;
    }),
  };
}

function boardExport(view: BoardView): CsvExportSource {
  return {
    name: "hip_governance_board",
    title: view.title,
    columns: [
      { key: "hip", label: "hip" },
      { key: "title", label: "title" },
      { key: "status", label: "status" },
      { key: "board_column", label: "board_column" },
    ],
    rows: view.columns.flatMap((column) =>
      column.items.map((item) => ({
        hip: item.key,
        title: item.title,
        status: item.status,
        board_column: column.title,
      })),
    ),
  };
}

export function ViewCards({
  views,
  sectionDocs,
  provenance,
}: {
  views: ViewDoc[];
  sectionDocs: SectionDoc[];
  provenance: Manifest["provenance"];
}) {
  const [jump, setJump] = useState<JumpRequest | null>(null);
  const jumpCounter = useRef(0);

  const matrix = views.find((view): view is MatrixView => view.kind === "matrix");
  const evidence = useMemo(() => {
    const evidenceDoc = matrix && sectionDocs.find((doc) => doc.id === matrix.evidence_section);
    return evidenceByCell(evidenceDoc?.rows ?? []);
  }, [matrix, sectionDocs]);

  return (
    <>
      {views.map((view) => {
        const exportSource = view.kind === "board" ? boardExport(view) : matrixExport(view);
        return (
          <SectionCard
            key={view.id}
            id={view.id}
            title={view.title}
            badge={view.badge}
            description={view.description}
            generatedAt={view.generated_at}
            stale={view.stale}
            actions={
              <>
                <CopyLinkButton sectionId={view.id} />
                <CsvDownloadButton
                  provenance={provenance}
                  payload={() => ({
                    ...exportSource,
                    total: exportSource.rows.length,
                    dataAsOf: view.generated_at,
                  })}
                />
              </>
            }
          >
            {view.kind === "board" ? (
              // The board names the view its chips jump to, so a future board
              // could target something other than the coverage matrix.
              <StatusBoard
                view={view}
                onJump={(hip) =>
                  view.target_view === matrix?.id && setJump({ hip, nonce: ++jumpCounter.current })
                }
              />
            ) : (
              <CoverageMatrix view={view} evidence={evidence} jump={jump} />
            )}
          </SectionCard>
        );
      })}
    </>
  );
}
