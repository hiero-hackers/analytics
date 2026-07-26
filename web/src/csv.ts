/**
 * Provenance-stamped CSV export of whatever rows a view is showing — mirrors
 * the legacy exportCSV preamble (view name, data watermark, code revision,
 * and "N of M" when the view is filtered).
 */

import type { ColumnSpec, Manifest, Row } from "./api";
import { stamp } from "./format";
import { csvSafe } from "./safety";

/** An export before the row-count context is attached (views build these). */
export type CsvExportSource = Omit<CsvExport, "total" | "dataAsOf">;

export interface CsvExport {
  name: string;
  title: string;
  columns: ColumnSpec[];
  rows: Row[];
  total: number;
  dataAsOf?: string;
}

/** One CSV field: neutralised against spreadsheet formulas, then quoted. */
const quote = (value: unknown) => {
  const text = csvSafe(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};

/** Trigger a browser download of prepared CSV text. */
function saveCsv(filename: string, text: string) {
  const blob = new Blob([text], { type: "text/csv" });
  const anchor = document.createElement("a");
  anchor.href = URL.createObjectURL(blob);
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(anchor.href);
}

/** The `# …` provenance preamble both download paths share. */
function preamble(title: string, dataAsOf: string | undefined, provenance: Manifest["provenance"]): string[] {
  const watermark = [
    dataAsOf && `data as of ${stamp(dataAsOf)}`,
    provenance.git_sha && `code ${provenance.git_sha}`,
  ]
    .filter(Boolean)
    .join(" · ");
  return [`# Hiero analytics — ${title}`, ...(watermark ? [`# ${watermark}`] : [])];
}

/**
 * Download a CSV shipped by the API (e.g. a chart's companion table) with the
 * provenance preamble stamped on top of its raw text.
 */
export function downloadCsvText(
  name: string,
  title: string,
  text: string,
  provenance: Manifest["provenance"],
  dataAsOf?: string,
) {
  saveCsv(name, [...preamble(title, dataAsOf, provenance), text.trimEnd()].join("\n") + "\n");
}

export function downloadCsv(payload: CsvExport, provenance: Manifest["provenance"]) {
  const lines = [
    ...preamble(payload.title, payload.dataAsOf, provenance),
    ...(payload.rows.length !== payload.total
      ? [`# ${payload.rows.length} of ${payload.total} rows (filtered view)`]
      : []),
    payload.columns.map((column) => quote(column.label)).join(","),
    ...payload.rows.map((row) => payload.columns.map((column) => quote(row[column.key])).join(",")),
  ];
  saveCsv(`${payload.name}.csv`, lines.join("\n"));
}
