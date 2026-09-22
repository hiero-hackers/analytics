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

import { useRef } from 'react';
import { flexRender } from '@tanstack/react-table';
import { useVirtualizer } from '@tanstack/react-virtual';
import type { DataTableInstance } from '../useDataTable';
import { PRINT_ROW_LIMIT, usePrintMode } from '../printContext';

// Typical rendered height of one row; the virtualiser corrects itself from
// real measurements as rows mount, so this only has to be close.
const ROW_HEIGHT = 27;
const OVERSCAN = 12;
/** Below this, a table renders whole — the DOM cost is already negligible. */
export const VIRTUALIZE_ABOVE = 100;

export function DataTable({ table }: { table: DataTableInstance }) {
  const printing = usePrintMode();
  const scrollRef = useRef<HTMLDivElement>(null);
  const rows = table.getRowModel().rows;
  const globalFilter = (table.state.globalFilter as string) ?? '';
  const virtualized = !printing && rows.length > VIRTUALIZE_ABOVE;
  const virtualizer = useVirtualizer({
    // Pause observation during printing, retaining the measured screen rows and offset.
    count: rows.length > VIRTUALIZE_ABOVE ? rows.length : 0,
    getScrollElement: () => (printing ? null : scrollRef.current),
    estimateSize: () => ROW_HEIGHT,
    overscan: OVERSCAN,
  });
  const virtualRows = virtualizer.getVirtualItems();
  const paddingTop = virtualized && virtualRows.length ? virtualRows[0].start : 0;
  const paddingBottom =
    virtualized && virtualRows.length
      ? virtualizer.getTotalSize() - virtualRows[virtualRows.length - 1].end
      : 0;
  const renderedRows = printing
    ? [
        ...rows.slice(0, PRINT_ROW_LIMIT),
        // Retain the screen viewport beyond the cap so its focused links survive printing.
        ...virtualRows
          .filter((item) => item.index >= PRINT_ROW_LIMIT)
          .map((item) => rows[item.index]),
      ]
    : virtualized
      ? virtualRows.map((item) => rows[item.index])
      : rows;
  const columnCount = table.getVisibleFlatColumns().length;

  return (
    <>
      {printing && globalFilter && (
        <p className="print-selection">
          Filter: “{globalFilter}”. {rows.length} of {table.options.data.length} rows match; rows
          outside this filter are not printed.
        </p>
      )}
      {printing && rows.length > PRINT_ROW_LIMIT && (
        <p className="print-selection" data-print-truncated>
          Showing {PRINT_ROW_LIMIT} of {rows.length} rows in the current order.{' '}
          {rows.length - PRINT_ROW_LIMIT} rows are not printed. Download CSV from this table on the
          dashboard for the complete selection.
        </p>
      )}
      <input
        data-print-hide
        className="search"
        placeholder="Filter…"
        aria-label="Filter rows"
        value={globalFilter}
        onChange={(event) => table.setGlobalFilter(event.target.value)}
      />
      <div className="tablewrap" ref={scrollRef} data-scroll-restore>
        <table>
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const sorted = header.column.getIsSorted() as string;
                  return (
                    <th
                      key={header.id}
                      className={header.column.columnDef.meta?.numeric ? 'num' : undefined}
                      aria-sort={
                        sorted === 'asc'
                          ? 'ascending'
                          : sorted === 'desc'
                            ? 'descending'
                            : undefined
                      }
                    >
                      {printing && flexRender(header.column.columnDef.header, header.getContext())}
                      <button
                        type="button"
                        className="thbtn"
                        hidden={printing}
                        data-print-hide
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {/* The mark's slot is always reserved so toggling sort never shifts the column. */}
                        <span className="sortmark" aria-hidden="true">
                          {{ asc: '↑', desc: '↓' }[sorted] ?? ''}
                        </span>
                      </button>
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={columnCount} className="py-6 text-center text-[13px] text-muted">
                  {globalFilter ? (
                    <>
                      {printing ? 'No rows match this filter.' : 'No rows match —'}{' '}
                      <button
                        type="button"
                        hidden={printing}
                        className="underline"
                        onClick={() => table.setGlobalFilter('')}
                      >
                        clear the filter?
                      </button>
                    </>
                  ) : (
                    'No rows to show.'
                  )}
                </td>
              </tr>
            )}
            {paddingTop > 0 && (
              <tr aria-hidden="true">
                <td colSpan={columnCount} style={{ height: paddingTop, padding: 0, border: 0 }} />
              </tr>
            )}
            {renderedRows.map((row, index) => (
              <tr
                key={row.id}
                hidden={printing && index >= PRINT_ROW_LIMIT}
                data-index={virtualized ? virtualRows[index].index : index}
                ref={virtualized ? virtualizer.measureElement : undefined}
              >
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    className={
                      cell.column.columnDef.meta?.numeric ||
                      (printing && typeof row.original[cell.column.id] === 'number')
                        ? 'num'
                        : undefined
                    }
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
            {paddingBottom > 0 && (
              <tr aria-hidden="true">
                <td
                  colSpan={columnCount}
                  style={{ height: paddingBottom, padding: 0, border: 0 }}
                />
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
