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

import { useRef, type ReactNode } from 'react';
import { flexRender } from '@tanstack/react-table';
import { useVirtualizer } from '@tanstack/react-virtual';
import { ArrowDownIcon, ArrowUpDownIcon, ArrowUpIcon, SearchIcon, XIcon } from 'lucide-react';
import { cn } from 'cn';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { PRINT_ROW_LIMIT, usePrintMode } from '../printContext';
import type { DataTableInstance } from '../useDataTable';

// Typical rendered height of one row; the virtualiser corrects itself from
// real measurements as rows mount, so this only has to be close.
const ROW_HEIGHT = 49;

/** Text reads left, numbers right in tabular figures so their digits line up. */
const align = (numeric?: boolean) => (numeric ? 'text-right tabular-nums' : undefined);
/** On narrow screens the first column stays in view; its cells need an opaque background. */
const STICKY_FIRST = 'max-md:sticky max-md:left-0 max-md:z-10';
const OVERSCAN = 12;
/** Below this, a table renders whole — the DOM cost is already negligible. */
export const VIRTUALIZE_ABOVE = 100;

export function DataTable({
  table,
  controls,
  actions,
  printColumns,
  printRowLimit = PRINT_ROW_LIMIT,
}: {
  table: DataTableInstance;
  /** Beside the search: the switches that choose which rows (a time range). */
  controls?: ReactNode;
  /** At the toolbar's end: what a reader does with the rows (download, an external link). */
  actions?: ReactNode;
  /** A detail view may print a concise set of columns while its CSV keeps the complete table. */
  printColumns?: string[];
  /** Maximum paper rows for this table; the full selection remains downloadable as CSV. */
  printRowLimit?: number;
}) {
  const printing = usePrintMode();
  const scrollRef = useRef<HTMLDivElement>(null);
  const rows = table.getRowModel().rows;
  const globalFilter = (table.state.globalFilter as string) ?? '';
  // Paper gets real rows, never a virtual window.
  const virtualized = !printing && rows.length > VIRTUALIZE_ABOVE;
  const virtualizer = useVirtualizer({
    // Observation pauses while printing, keeping the screen measurements and
    // offset: restoring against the shorter printed table would lose them.
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
  const visibleRows = printing
    ? [
        ...rows.slice(0, printRowLimit),
        // The screen viewport beyond the cap stays mounted (hidden) so its focused links survive.
        ...virtualRows
          .filter((item) => item.index >= printRowLimit)
          .map((item) => rows[item.index]),
      ]
    : virtualized
      ? virtualRows.map((item) => rows[item.index])
      : rows;
  const columnCount =
    printing && printColumns
      ? table.getVisibleFlatColumns().filter((column) => printColumns.includes(column.id)).length
      : table.getVisibleFlatColumns().length;
  const total = table.getCoreRowModel().rows.length;
  const count = (n: number) => n.toLocaleString('en-US');

  return (
    <>
      {printing && globalFilter && (
        <p className="print-selection">
          Filter: “{globalFilter}”. {count(rows.length)} of {count(total)} rows match; rows outside
          this filter are not printed.
        </p>
      )}
      {printing && rows.length > printRowLimit && (
        <p className="print-selection" data-print-truncated>
          Showing {count(printRowLimit)} of {count(rows.length)} rows in the current order.{' '}
          {count(rows.length - printRowLimit)} rows are not printed. Download CSV from this table on
          the dashboard for the complete selection.
        </p>
      )}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative w-full sm:w-64" hidden={printing} data-print-hide>
          <SearchIcon
            aria-hidden="true"
            className="pointer-events-none absolute top-2 left-2.5 size-4 text-muted-foreground"
          />
          <Input
            placeholder="Search this table…"
            aria-label="Filter rows"
            value={globalFilter}
            onChange={(event) => table.setGlobalFilter(event.target.value)}
            className="h-8 bg-background pr-8 pl-8 text-xs"
          />
          {globalFilter && (
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label="Clear filter"
              className="absolute top-1.5 right-1.5"
              onClick={() => table.setGlobalFilter('')}
            >
              <XIcon />
            </Button>
          )}
        </div>
        {controls}
        <div className="flex flex-wrap items-center gap-2 sm:ml-auto">
          <span role="status" className="text-xs text-muted-foreground tabular-nums">
            {rows.length === total
              ? `${count(total)} ${total === 1 ? 'row' : 'rows'}`
              : `${count(rows.length)} of ${count(total)} rows`}
          </span>
          {actions}
        </div>
      </div>
      <Table
        containerRef={scrollRef}
        // Capped height so a long table never traps the page scroll.
        containerClassName="max-h-[min(520px,60dvh)] overflow-auto rounded-lg border"
      >
        <TableHeader className="sticky top-0 z-20">
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id} className="hover:bg-transparent">
              {headerGroup.headers.map((header, index) => {
                if (printing && printColumns && !printColumns.includes(header.column.id))
                  return null;
                const sorted = header.column.getIsSorted() as string;
                const numeric = header.column.columnDef.meta?.numeric;
                const SortIcon =
                  sorted === 'asc'
                    ? ArrowUpIcon
                    : sorted === 'desc'
                      ? ArrowDownIcon
                      : ArrowUpDownIcon;
                return (
                  <TableHead
                    key={header.id}
                    data-numeric={numeric || undefined}
                    aria-sort={
                      sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : undefined
                    }
                    className={cn(
                      'h-10 border-b bg-muted/85 px-4 text-xs font-medium backdrop-blur-sm',
                      sorted ? 'text-foreground' : 'text-muted-foreground',
                      align(numeric),
                      index === 0 && STICKY_FIRST,
                    )}
                  >
                    {printing && (
                      <span className="first-letter:uppercase">
                        {flexRender(header.column.columnDef.header, header.getContext())}
                      </span>
                    )}
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      hidden={printing}
                      data-print-hide
                      className={cn(
                        'group/sort -mx-2 h-7 px-2 font-medium text-inherit hover:bg-background/70',
                        numeric && 'flex-row-reverse',
                      )}
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      {/* CSS sentence case keeps the accessible name as published. */}
                      <span className="first-letter:uppercase">
                        {flexRender(header.column.columnDef.header, header.getContext())}
                      </span>
                      {/* Always an icon, so sorting never shifts the column. */}
                      <SortIcon
                        data-icon={numeric ? 'inline-start' : 'inline-end'}
                        aria-hidden="true"
                        className={cn(
                          'transition-opacity',
                          sorted ? 'text-link' : 'opacity-30 group-hover/sort:opacity-70',
                        )}
                      />
                    </Button>
                  </TableHead>
                );
              })}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {rows.length === 0 && (
            <TableRow className="hover:bg-transparent">
              <TableCell colSpan={columnCount} className="py-6 text-center text-muted-foreground">
                {globalFilter ? (
                  <>
                    {printing ? 'No rows match this filter.' : 'No rows match —'}{' '}
                    <Button
                      type="button"
                      variant="link"
                      size="sm"
                      hidden={printing}
                      data-print-hide
                      className="px-0"
                      onClick={() => table.setGlobalFilter('')}
                    >
                      clear the filter?
                    </Button>
                  </>
                ) : (
                  'No rows to show.'
                )}
              </TableCell>
            </TableRow>
          )}
          {paddingTop > 0 && (
            <tr aria-hidden="true">
              <td colSpan={columnCount} style={{ height: paddingTop, padding: 0, border: 0 }} />
            </tr>
          )}
          {visibleRows.map((row, index) => (
            <TableRow
              key={row.id}
              className="border-row-line even:bg-muted/20 hover:bg-link/5"
              hidden={printing && index >= printRowLimit}
              data-index={virtualized ? virtualRows[index].index : index}
              ref={virtualized ? virtualizer.measureElement : undefined}
            >
              {row.getVisibleCells().map((cell, cellIndex) => {
                if (printing && printColumns && !printColumns.includes(cell.column.id)) return null;
                // On paper any number aligns right, declared numeric or not.
                const numeric =
                  cell.column.columnDef.meta?.numeric ||
                  (printing && typeof row.original[cell.column.id] === 'number');
                return (
                  <TableCell
                    key={cell.id}
                    data-numeric={numeric || undefined}
                    className={cn(
                      'px-4 py-2.5',
                      align(numeric),
                      cellIndex === 0 && ['font-medium max-md:bg-card', STICKY_FIRST],
                    )}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                );
              })}
            </TableRow>
          ))}
          {paddingBottom > 0 && (
            <tr aria-hidden="true">
              <td colSpan={columnCount} style={{ height: paddingBottom, padding: 0, border: 0 }} />
            </tr>
          )}
        </TableBody>
      </Table>
    </>
  );
}
