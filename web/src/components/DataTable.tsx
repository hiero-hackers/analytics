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
import type { DataTableInstance } from '../useDataTable';

// Typical rendered height of one row; the virtualiser corrects itself from
// real measurements as rows mount, so this only has to be close.
const ROW_HEIGHT = 49;

/** Text reads left, numbers right in tabular figures so their digits line up. */
const align = (numeric?: boolean) => (numeric ? 'text-right tabular-nums' : undefined);
/** On narrow screens the first column (who/what the row is) stays in view while
 *  the rest scrolls sideways; it needs an opaque ground to scroll under. */
const STICKY_FIRST = 'max-md:sticky max-md:left-0 max-md:z-10';
const OVERSCAN = 12;
/** Below this, a table renders whole — the DOM cost is already negligible. */
export const VIRTUALIZE_ABOVE = 100;

export function DataTable({ table }: { table: DataTableInstance }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const rows = table.getRowModel().rows;
  const globalFilter = (table.state.globalFilter as string) ?? '';
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
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="relative w-full sm:max-w-xs">
          <SearchIcon
            aria-hidden="true"
            className="pointer-events-none absolute top-2.5 left-3 size-4 text-muted-foreground"
          />
          <Input
            placeholder="Search this table…"
            aria-label="Filter rows"
            value={globalFilter}
            onChange={(event) => table.setGlobalFilter(event.target.value)}
            className="h-9 bg-background pl-9 pr-9"
          />
          {globalFilter && (
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Clear filter"
              className="absolute top-0.5 right-0.5"
              onClick={() => table.setGlobalFilter('')}
            >
              <XIcon />
            </Button>
          )}
        </div>
        <span role="status" className="text-xs text-muted-foreground tabular-nums">
          {rows.length.toLocaleString('en-US')} {globalFilter ? 'matching' : 'total'} rows
        </span>
      </div>
      <Table
        containerRef={scrollRef}
        // The scroll box: capped at 520px or 60% of the dynamic viewport,
        // whichever is less, so a long table never traps the page scroll.
        containerClassName="max-h-[min(520px,60dvh)] overflow-auto rounded-lg border"
      >
        <TableHeader className="sticky top-0 z-20">
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id} className="hover:bg-transparent">
              {headerGroup.headers.map((header, index) => {
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
                      'bg-muted px-4 py-2 text-xs',
                      align(numeric),
                      index === 0 && STICKY_FIRST,
                    )}
                  >
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className={cn('-mx-2', numeric && 'flex-row-reverse')}
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {/* Always an icon, so sorting never shifts the column. */}
                      <SortIcon
                        data-icon={numeric ? 'inline-start' : 'inline-end'}
                        aria-hidden="true"
                        className={sorted ? undefined : 'opacity-40'}
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
                    No rows match —{' '}
                    <Button
                      type="button"
                      variant="link"
                      size="sm"
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
              className="even:bg-muted/25 hover:bg-link/5"
              data-index={virtualized ? virtualRows[index].index : index}
              ref={virtualized ? virtualizer.measureElement : undefined}
            >
              {row.getVisibleCells().map((cell, cellIndex) => {
                const numeric = cell.column.columnDef.meta?.numeric;
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
