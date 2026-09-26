/**
 * The page footer's code revision. The data watermark ("Data as of …") lives
 * in the header, where it is visible without scrolling; this names the code
 * that rendered it.
 */

import type { Manifest } from '../api';

export function ProvenanceFooter({ provenance }: { provenance: Manifest['provenance'] }) {
  if (!provenance.git_sha) return null;
  return (
    <footer className="ml-auto text-xs text-soft tabular-nums">Code {provenance.git_sha}</footer>
  );
}
