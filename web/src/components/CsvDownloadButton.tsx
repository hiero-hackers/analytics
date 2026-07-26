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
      Download CSV
    </button>
  );
}
