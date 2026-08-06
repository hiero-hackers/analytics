/** The "Download CSV" button — builds its payload lazily on click. */

import type { Manifest } from "../api";
import { downloadCsv, type CsvExport } from "../csv";

export function CsvDownloadButton({
  payload,
  provenance,
}: {
  payload: () => CsvExport;
  provenance: Manifest["provenance"];
}) {
  return (
    <button className="dl" onClick={() => downloadCsv(payload(), provenance)}>
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
        <path d="M8 2v8m0 0 3-3m-3 3L5 7" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M2.5 11v1.5a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1V11" strokeLinecap="round" />
      </svg>
      Download CSV
    </button>
  );
}
