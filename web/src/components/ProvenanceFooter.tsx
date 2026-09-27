/** The page footer's code revision; the data watermark lives in the header. */

import type { Manifest } from '../api';

export function ProvenanceFooter({ provenance }: { provenance: Manifest['provenance'] }) {
  if (!provenance.git_sha) return null;
  return (
    <footer className="ml-auto text-xs text-soft tabular-nums">Code {provenance.git_sha}</footer>
  );
}
