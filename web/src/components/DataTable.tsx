/**
 * The sortable/filterable table body (filter input, sortable headers, rows)
 * for a table built with `useDataTable` — decoupled from section documents so
 * bespoke views (the HIP evidence panel, future drill-downs) reuse it without
 * being "sections".
 *
 * Long tables are virtualised: the biggest run to thousands of rows while the
 * scroll box only ever shows ~15, so rendering the rest costs DOM for nothing.
 * Above `VIRTUALIZE_ABOVE` rows only the visible window (plus overscan) is
 * mounted, with spacer rows standing in for the scroll height above and below;
 * shorter tables render whole, since the machinery would cost more than it
 * saves. Sorting, filtering, and CSV export always see every row — this is
 * purely about what reaches the DOM.
 */

import { useRef } from "react";
import { flexRender, type Table } from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { Row } from "../api";

// Typical rendered height of one row; the virtualiser corrects itself from
// real measurements as rows mount, so this only has to be close.
const ROW_HEIGHT = 27;
const OVERSCAN = 12;
/** Below this, a table renders whole — the DOM cost is already negligible. */
export const VIRTUALIZE_ABOVE = 100;

export function DataTable({ table }: { table: Table<Row> }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const rows = table.getRowModel().rows;
  const virtualized = rows.length > VIRTUALIZE_ABOVE;
  const virtualizer = useVirtualizer({
    count: virtualized ? rows.length : 0,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: OVERSCAN,
  });
  const virtualRows = virtualizer.getVirtualItems();
  const paddingTop = virtualized && virtualRows.length ? virtualRows[0].start : 0;
  const paddingBottom =
    virtualized && virtualRows.length
      ? virtualizer.getTotalSize() - virtualRows[virtualRows.length - 1].end
      : 0;
  const visibleRows = virtualized ? virtualRows.map((item) => rows[item.index]) : rows;
  const columnCount = table.getVisibleFlatColumns().length;

  return (
    <>
      <input
        className="search"
        placeholder="Filter…"
        value={(table.getState().globalFilter as string) ?? ""}
        onChange={(event) => table.setGlobalFilter(event.target.value)}
      />
      <div className="tablewrap" ref={scrollRef}>
        <table>
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th key={header.id} onClick={header.column.getToggleSortingHandler()}>
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    {{ asc: " ↑", desc: " ↓" }[header.column.getIsSorted() as string] ?? ""}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {paddingTop > 0 && (
              <tr aria-hidden="true">
                <td colSpan={columnCount} style={{ height: paddingTop, padding: 0, border: 0 }} />
              </tr>
            )}
            {visibleRows.map((row, index) => (
              <tr
                key={row.id}
                data-index={virtualized ? virtualRows[index].index : index}
                ref={virtualized ? virtualizer.measureElement : undefined}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                ))}
              </tr>
            ))}
            {paddingBottom > 0 && (
              <tr aria-hidden="true">
                <td colSpan={columnCount} style={{ height: paddingBottom, padding: 0, border: 0 }} />
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
