/**
 * One spec-listed section as a card: the shared card chrome, a
 * provenance-stamped CSV export, period tabs, and the sortable/filterable
 * table core.
 */

import { useState } from 'react';
import type { Manifest, SectionDoc } from '../api';
import { safeUrl } from '../safety';
import { useDataTable } from '../useDataTable';
import { CopyLinkButton } from './CopyLinkButton';
import { CsvDownloadButton } from './CsvDownloadButton';
import { DataTable } from './DataTable';
import { PeriodTabs } from './PeriodTabs';
import { SectionCard } from './SectionCard';

export function SectionTable({
  doc,
  provenance,
  periodLabels,
}: {
  doc: SectionDoc;
  provenance: Manifest['provenance'];
  periodLabels?: Record<string, string>;
}) {
  const [period, setPeriod] = useState<string | null>(null);
  const rows = period && doc.periods ? doc.periods[period] : doc.rows;
  const table = useDataTable(doc.columns, rows, doc.id);
  const shown = table.getRowModel().rows.length;
  const action = doc.action ? safeUrl(doc.action.url) : null;

  return (
    <SectionCard
      id={doc.id}
      title={doc.title}
      badge={shown === rows.length ? `${rows.length} rows` : `${shown} of ${rows.length}`}
      description={doc.description}
      generatedAt={doc.generated_at}
      stale={doc.stale}
      actions={
        <>
          <CopyLinkButton sectionId={doc.id} />
          {action && (
            <a className="dl" href={action} target="_blank" rel="noopener noreferrer">
              {doc.action?.label}
            </a>
          )}
          <CsvDownloadButton
            provenance={provenance}
            payload={() => ({
              name: doc.id,
              title: doc.title,
              columns: doc.columns,
              rows: table.getRowModel().rows.map((row) => row.original),
              total: rows.length,
              dataAsOf: doc.generated_at,
            })}
          />
        </>
      }
    >
      <PeriodTabs
        periods={Object.keys(doc.periods ?? {})}
        active={period}
        onChange={setPeriod}
        labels={periodLabels}
      />
      <DataTable table={table} />
    </SectionCard>
  );
}
