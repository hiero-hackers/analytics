/** The page-level provenance line: data watermark and code revision. */

import type { Manifest } from '../api';
import { provenanceLine } from '../printUtils';

export function ProvenanceFooter({ provenance }: { provenance: Manifest['provenance'] }) {
  return <footer className="provenance">{provenanceLine(provenance)}</footer>;
}
