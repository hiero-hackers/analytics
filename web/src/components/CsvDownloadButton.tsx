/** The "Download CSV" button — builds (or fetches) its payload lazily on click. */

import { DownloadIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { Manifest } from '../api';
import { downloadCsv, type CsvExport } from '../csv';

/** The button itself, for callers whose download is not a CsvExport (a chart's companion file). */
export function DownloadButton({
  onClick,
  compact = false,
}: {
  onClick: () => void;
  /** Icon-only below the enclosing `@container`'s `lg` width (a narrow chart card). */
  compact?: boolean;
}) {
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={onClick}
      aria-label={compact ? 'Download CSV' : undefined}
      title={compact ? 'Download CSV' : undefined}
    >
      <DownloadIcon data-icon="inline-start" />
      {compact ? <span className="hidden @lg:inline">Download CSV</span> : 'Download CSV'}
    </Button>
  );
}

export function CsvDownloadButton({
  payload,
  provenance,
  compact,
}: {
  payload: () => CsvExport;
  provenance: Manifest['provenance'];
  compact?: boolean;
}) {
  return <DownloadButton compact={compact} onClick={() => downloadCsv(payload(), provenance)} />;
}
