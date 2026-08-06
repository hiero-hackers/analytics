/**
 * The shared TanStack table setup: column specs become accessors with
 * legacy-matching sort values and formatted cells, with global filtering
 * wired in. Any view rendering API rows builds its table through this.
 */

import { useMemo, useState } from "react";
import {
  createColumnHelper,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type Table,
} from "@tanstack/react-table";
import type { ColumnSpec, Row } from "./api";
import { FormattedCell } from "./components/FormattedCell";

// Column meta this app attaches: numeric columns right-align (header and
// cells) via DataTable.
declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- interface merging requires the type params
  interface ColumnMeta<TData, TValue> {
    numeric?: boolean;
  }
}

/** Sortable value: raw for numbers, string otherwise (matches legacy sort). */
function sortableValue(row: Row, key: string): number | string {
  const value = row[key];
  if (typeof value === "number") return value;
  return value === null || value === undefined ? "" : String(value);
}

export function useDataTable(columns: ColumnSpec[], rows: Row[], columnsKey: string): Table<Row> {
  const [filter, setFilter] = useState("");
  const helper = createColumnHelper<Row>();
  const tableColumns = useMemo(
    () =>
      columns.map((spec: ColumnSpec) =>
        helper.accessor((row) => sortableValue(row, spec.key), {
          id: spec.key,
          header: spec.label,
          cell: (context) => <FormattedCell value={context.row.original[spec.key]} format={spec.format} />,
          meta: { numeric: spec.format === "number" },
        }),
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- columns derive from the key
    [columnsKey],
  );
  return useReactTable({
    data: rows,
    columns: tableColumns,
    state: { globalFilter: filter },
    onGlobalFilterChange: setFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });
}
