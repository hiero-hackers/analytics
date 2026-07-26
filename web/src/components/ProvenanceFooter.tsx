/** The page-level provenance line: data watermark and code revision. */

import type { Manifest } from "../api";
import { stamp } from "../format";

export function ProvenanceFooter({ provenance }: { provenance: Manifest["provenance"] }) {
  const line = [
    provenance.data_as_of && `data ${stamp(provenance.data_as_of)} UTC`,
    provenance.git_sha && `code ${provenance.git_sha}`,
  ]
    .filter(Boolean)
    .join(" · ");
  return <footer className="provenance">{line}</footer>;
}
