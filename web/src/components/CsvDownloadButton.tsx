/** The "Download CSV" button — builds (or fetches) its payload lazily on click. */

import { DownloadIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { Manifest } from '../api';
import { downloadCsv, type CsvExport } from '../csv';

/** The button itself, for callers whose download is not a CsvExport (a chart's companion file). */
export function DownloadButton({ onClick }: { onClick: () => void }) {
  return (
    <Button type="button" variant="outline" size="sm" onClick={onClick}>
      <DownloadIcon data-icon="inline-start" />
      Download CSV
    </Button>
  );
}

export function CsvDownloadButton({
  payload,
  provenance,
}: {
  payload: () => CsvExport;
  provenance: Manifest['provenance'];
}) {
  return <DownloadButton onClick={() => downloadCsv(payload(), provenance)} />;
}
