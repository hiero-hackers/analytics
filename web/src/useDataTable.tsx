/**
 * The shared TanStack table setup: column specs become accessors with
 * legacy-matching sort values and formatted cells, with global filtering
 * wired in. Any view rendering API rows builds its table through this.
 */

import { useMemo, useState } from 'react';
import {
  columnFilteringFeature,
  columnVisibilityFeature,
  createColumnHelper,
  createFilteredRowModel,
  createSortedRowModel,
  filterFn_includesString,
  globalFilteringFeature,
  rowSortingFeature,
  sortFn_alphanumeric,
  sortFn_basic,
  sortFn_text,
  tableFeatures,
  useTable,
  type ReactTable,
} from '@tanstack/react-table';
import type { ColumnSpec, Row } from './api';
import { FormattedCell } from './components/FormattedCell';

/**
 * v9 bundles nothing by default: every feature, row model, and sort/filter
 * function this app touches is registered here, and nothing else ships.
 * Only the global filter box is used, but `globalFilteringFeature` and the
 * filtered row model both declare `columnFilteringFeature` a prerequisite, so
 * it comes along; `includesString` is what global filtering defaults to. The
 * sort functions are the three `getAutoSortFn` can pick for the
 * `number | string` values `sortableValue` produces — dates never occur, so
 * `datetime` is left out.
 */
const features = tableFeatures({
  columnFilteringFeature,
  columnVisibilityFeature,
  globalFilteringFeature,
  rowSortingFeature,
  filteredRowModel: createFilteredRowModel(),
  sortedRowModel: createSortedRowModel(),
  filterFns: { includesString: filterFn_includesString },
  sortFns: {
    alphanumeric: sortFn_alphanumeric,
    basic: sortFn_basic,
    text: sortFn_text,
  },
});

export type DataTableFeatures = typeof features;

/** The table instance `useDataTable` hands back — what every table view renders from. */
export type DataTableInstance = ReactTable<DataTableFeatures, Row>;

// Column meta this app attaches: whether the column holds numbers, which earns
// it tabular figures so digits keep a constant width. Alignment itself is not
// per-column — every cell centres (see the `th`/`td` rules).
declare module '@tanstack/react-table' {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- interface merging requires the type params
  interface ColumnMeta<TFeatures, TData, TValue> {
    numeric?: boolean;
  }
}

/** Sortable value: raw for numbers, string otherwise (matches legacy sort). */
function sortableValue(row: Row, key: string): number | string {
  const value = row[key];
  if (typeof value === 'number') return value;
  return value === null || value === undefined ? '' : String(value);
}

export function useDataTable(
  columns: ColumnSpec[],
  rows: Row[],
  columnsKey: string,
): DataTableInstance {
  const [filter, setFilter] = useState('');
  const helper = createColumnHelper<DataTableFeatures, Row>();
  const tableColumns = useMemo(
    () =>
      columns.map((spec: ColumnSpec) =>
        helper.accessor((row): unknown => sortableValue(row, spec.key), {
          id: spec.key,
          header: spec.label,
          cell: (context) => (
            <FormattedCell value={context.row.original[spec.key]} format={spec.format} />
          ),
          meta: { numeric: spec.format === 'number' },
        }),
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- columns derive from the key
    [columnsKey],
  );
  return useTable({
    features,
    data: rows,
    columns: tableColumns,
    state: { globalFilter: filter },
    onGlobalFilterChange: setFilter,
  });
}
