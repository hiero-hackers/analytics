/**
 * One spec-listed section as a card: the shared card chrome, a
 * provenance-stamped CSV export, role tabs, period tabs, and the
 * sortable/filterable table core.
 *
 * A section that publishes role `variants` renders as one tabbed card rather
 * than a stack of near-identical ones. Each variant is a full table of its own
 * — the count column is named for the role it counts — so the columns, rows,
 * description, freshness stamp and export all follow the active tab.
 */

import { useEffect, useState } from 'react';
import { CrosshairIcon, ExternalLinkIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { Manifest, SectionDoc, SectionVariant } from '../api';
import { DIMENSION_LABELS, dimensionOf, matches, useFocus } from '../focus';
import { safeUrl } from '../safety';
import { useDataTable } from '../useDataTable';
import { useHashState } from '../useHashState';
import { CopyLinkButton } from './CopyLinkButton';
import { CsvDownloadButton } from './CsvDownloadButton';
import { DataTable } from './DataTable';
import { PeriodTabs } from './PeriodTabs';
import { SectionCard } from './SectionCard';
import { VariantTabs } from './VariantTabs';

/** The document's own table as a variant, for sections with no role tabs. */
const soleVariant = (doc: SectionDoc): SectionVariant => ({ ...doc, label: '' });

export function SectionTable({
  doc,
  provenance,
  periodLabels,
}: {
  doc: SectionDoc;
  provenance: Manifest['provenance'];
  periodLabels?: Record<string, string>;
}) {
  const variants = doc.variants ?? [soleVariant(doc)];
  // A shared link names a section id, and an absorbed variant kept its own —
  // `#widget=committeraffiliations` has to land on this card with the
  // Committers tab active, not on the maintainer table the card opens with.
  const [widget] = useHashState('widget', '');
  const [index, setIndex] = useState(() =>
    Math.max(
      0,
      variants.findIndex((v) => v.id === widget),
    ),
  );
  const [period, setPeriod] = useState<string | null>(null);
  useEffect(() => {
    const linked = variants.findIndex((variant) => variant.id === widget);
    if (linked >= 0) setIndex(linked);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- variants derive from the doc
  }, [widget, doc]);

  const active = variants[Math.min(index, variants.length - 1)];
  // The tabs carry independent row sets, so a period the previous tab offered
  // may not exist on this one; fall back to its all-time rows rather than
  // rendering an undefined table.
  const periodRows = (period && active.periods?.[period]) || active.rows;
  // The dashboard focus narrows this table only when it has that column (a
  // repository focus leaves a per-person table alone, and says nothing).
  const [focus, setFocus] = useFocus();
  const focusColumn = focus
    ? active.columns.find((column) => dimensionOf(column.key) === focus.dimension)
    : undefined;
  const rows = focusColumn
    ? periodRows.filter((row) => matches(focus, focus!.dimension, row[focusColumn.key]))
    : periodRows;
  const table = useDataTable(active.columns, rows, active.id);
  const shown = table.getRowModel().rows.length;
  const action = active.action ? safeUrl(active.action.url) : null;

  return (
    <SectionCard
      id={doc.id}
      title={doc.title}
      badge={
        shown === periodRows.length
          ? `${periodRows.length} rows`
          : `${shown} of ${periodRows.length}`
      }
      description={active.description}
      generatedAt={active.generated_at}
      stale={active.stale}
      actions={
        <>
          {/* The link names the active tab, so what a reader shares is what
              they are looking at. */}
          <CopyLinkButton sectionId={active.id} />
          {action && (
            <Button asChild variant="outline" size="sm">
              <a href={action} target="_blank" rel="noopener noreferrer">
                <ExternalLinkIcon data-icon="inline-start" />
                {active.action?.label}
              </a>
            </Button>
          )}
          <CsvDownloadButton
            provenance={provenance}
            payload={() => ({
              name: active.id,
              title: active.title,
              columns: active.columns,
              rows: table.getRowModel().rows.map((row) => row.original),
              // "N of M" in the preamble: the focus and the search both narrow the export.
              total: periodRows.length,
              dataAsOf: active.generated_at,
            })}
          />
        </>
      }
    >
      <VariantTabs
        labels={variants.map((variant) => variant.label)}
        active={index}
        onSelect={setIndex}
        ariaLabel="Role"
      />
      <PeriodTabs
        periods={Object.keys(active.periods ?? {})}
        active={period}
        onChange={setPeriod}
        labels={periodLabels}
      />
      {focus && focusColumn && (
        <p
          role="status"
          className="mb-3 flex flex-wrap items-center gap-2 rounded-md border border-link/40 bg-link/5 px-3 py-2 text-xs"
        >
          <CrosshairIcon className="size-3.5 text-link" aria-hidden="true" />
          {/* One text run: the flex gap would otherwise split "name: n of m". */}
          <span>
            Filtered to {DIMENSION_LABELS[focus.dimension]} <strong>{focus.value}</strong>:{' '}
            {rows.length} of {periodRows.length} rows.
          </span>
          <Button
            variant="link"
            size="sm"
            className="h-auto p-0 text-xs"
            onClick={() => setFocus(null)}
          >
            Clear focus
          </Button>
        </p>
      )}
      <DataTable table={table} />
    </SectionCard>
  );
}
