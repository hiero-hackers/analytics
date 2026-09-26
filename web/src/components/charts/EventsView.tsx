/**
 * The `events` kind: one mark per timestamped event (a release) on a time
 * axis, one row per repository, busiest at the top — the PNG's layout, with
 * each release's tag and exact time on hover and in the data view.
 */

import { CartesianGrid, Cell, Scatter, ScatterChart, XAxis, YAxis, ZAxis } from 'recharts';
import { Button } from '@/components/ui/button';
import { ChartContainer, ChartTooltip, type ChartConfig } from '@/components/ui/chart';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { ColumnSpec, EventsDocument, Row } from '../../api';
import { dimensionOf, matches, toggle, useFocus } from '../../focus';
import { stamp } from '../../format';
import { useUrlList } from '../../urlState';
import { ChartShell, TABLE_CONTAINER, type ViewProps } from './ChartShell';
import { integer, plural, shorten, windowText } from './format';

const ROW_HEIGHT = 28;
const AXIS_HEIGHT = 48;
const DAY = 86_400_000;

type Point = Row & { t: number; y: number };

export function EventsView({ data, title, period, provenance }: ViewProps<EventsDocument>) {
  const [hidden, setHidden] = useUrlList(`${data.id}.hide`);
  const [focus, setFocus] = useFocus();
  const key = data.category.key;
  const dimension = dimensionOf(key);
  const isFocused = (row: Row) => matches(focus, dimension, row[key]);
  const anyFocused = data.rows.some(isFocused);
  const visible = data.types.filter((type) => !hidden.includes(type.key));
  const rows = data.rows.filter((row) => !hidden.includes(String(row.type)));
  // Row order follows the whole window's counts, so toggling a type never reshuffles rows.
  const order = data.categories;
  const counts = new Map(order.map((name) => [name, 0]));
  for (const row of rows) counts.set(String(row[key]), (counts.get(String(row[key])) ?? 0) + 1);
  const index = new Map(order.map((name, i) => [name, order.length - 1 - i]));
  const points = (type: string): Point[] =>
    rows
      .filter((row) => row.type === type)
      .map((row) => ({ ...row, t: Date.parse(String(row.time)), y: index.get(String(row[key]))! }));

  // The exporter always sets the end; the latest event is the fallback for older documents.
  const end = data.window.end
    ? Date.parse(data.window.end)
    : Math.max(0, ...data.rows.map((row) => Date.parse(String(row.time))));
  const start = end - (data.window.days ?? 365) * DAY;
  const long = (data.window.days ?? 0) > 120;
  const tick = new Intl.DateTimeFormat('en-US', {
    timeZone: 'UTC',
    month: 'short',
    ...(long ? { year: '2-digit' as const } : { day: 'numeric' as const }),
  });
  const config: ChartConfig = Object.fromEntries(
    data.types.map((type) => [type.key, { label: type.label }]),
  );
  const typeLabel = new Map(data.types.map((type) => [type.key, type.label]));
  const nouns = plural(data.category.label);

  const columns: ColumnSpec[] = [
    { key: 'time', label: 'Published (UTC)' },
    { key, label: data.category.label },
    { key: data.label.key, label: data.label.label },
    { key: 'type', label: 'Type' },
  ];
  const tableRows: Row[] = [...rows]
    .sort((a, b) => String(b.time).localeCompare(String(a.time)))
    .map((row) => ({ ...row, type: typeLabel.get(String(row.type)) ?? row.type }));

  const controls =
    data.types.length > 1 ? (
      <div className="flex flex-wrap gap-2" role="group" aria-label="Visible release types">
        {data.types.map((type) => (
          <Button
            key={type.key}
            size="sm"
            variant="outline"
            aria-pressed={!hidden.includes(type.key)}
            disabled={visible.length === 1 && visible[0].key === type.key}
            className={hidden.includes(type.key) ? 'opacity-50' : 'bg-card'}
            onClick={() =>
              setHidden(
                hidden.includes(type.key)
                  ? hidden.filter((k) => k !== type.key)
                  : [...hidden, type.key],
              )
            }
          >
            <span
              className={type.key === 'prerelease' ? 'size-2.5 rotate-45' : 'size-2.5 rounded-full'}
              style={{ backgroundColor: type.color }}
            />
            {type.label}
          </Button>
        ))}
      </div>
    ) : null;

  const chart = () => (
    <>
      <ChartContainer
        config={config}
        className="aspect-auto w-full"
        style={{ height: Math.max(order.length, 3) * ROW_HEIGHT + AXIS_HEIGHT }}
        aria-label={`${title}: ${integer.format(rows.length)} releases across ${order.length} ${nouns}. Choose Data for the full list.`}
      >
        <ScatterChart margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
          <CartesianGrid horizontal={false} strokeDasharray="3 3" />
          <XAxis
            type="number"
            dataKey="t"
            domain={[start, end]}
            scale="time"
            tickLine={false}
            axisLine={false}
            minTickGap={32}
            tickFormatter={(value) => tick.format(new Date(Number(value)))}
          />
          <YAxis
            type="number"
            dataKey="y"
            domain={[-0.5, order.length - 0.5]}
            ticks={order.map((_, i) => i)}
            interval={0}
            tickLine={false}
            axisLine={false}
            width={190}
            tickFormatter={(value) => {
              const name = order[order.length - 1 - Number(value)];
              return name ? `${shorten(name, 22)} (${counts.get(name) ?? 0})` : '';
            }}
          />
          <ZAxis range={[48, 48]} />
          <ChartTooltip
            cursor={false}
            content={({ active, payload }) => {
              const point = payload?.[0]?.payload as Point | undefined;
              if (!active || !point) return null;
              return (
                <div className="grid gap-1 rounded-lg border bg-card px-3 py-2 text-xs shadow-xl">
                  <p className="font-medium">{String(point[data.label.key]) || '(untagged)'}</p>
                  <p className="text-muted-foreground">{String(point[key])}</p>
                  <p className="tabular-nums">{stamp(String(point.time))} UTC</p>
                  <p>{typeLabel.get(String(point.type))}</p>
                </div>
              );
            }}
          />
          {visible.map((type) => (
            <Scatter
              key={type.key}
              name={type.label}
              data={points(type.key)}
              fill={type.color}
              fillOpacity={type.key === 'prerelease' ? 0.7 : 0.55}
              shape={type.key === 'prerelease' ? 'diamond' : 'circle'}
              isAnimationActive={false}
              className={dimension ? 'cursor-pointer' : undefined}
              onClick={
                dimension
                  ? (point: { payload?: Point }) =>
                      point.payload && setFocus(toggle(focus, dimension, point.payload[key]))
                  : undefined
              }
            >
              {anyFocused &&
                points(type.key).map((point) => (
                  <Cell
                    key={`${String(point[key])}|${String(point.time)}`}
                    fillOpacity={isFocused(point) ? 0.9 : 0.12}
                  />
                ))}
            </Scatter>
          ))}
        </ScatterChart>
      </ChartContainer>
      <p className="text-xs text-muted-foreground">
        Each mark is one release; the number beside a repository is its count in this window.
      </p>
    </>
  );

  const table = (
    <Table containerClassName={TABLE_CONTAINER}>
      <TableHeader className="sticky top-0 bg-muted">
        <TableRow>
          {columns.map((column) => (
            <TableHead key={column.key}>{column.label}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {tableRows.map((row) => (
          <TableRow
            key={`${String(row[key])}|${String(row[data.label.key])}|${String(row.time)}`}
            className={isFocused(row) ? 'bg-link/10' : undefined}
          >
            <TableCell className="tabular-nums">{stamp(String(row.time))}</TableCell>
            <TableCell className="font-medium">{String(row[key])}</TableCell>
            <TableCell>{String(row[data.label.key])}</TableCell>
            <TableCell>{String(row.type)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );

  return (
    <ChartShell
      data={data}
      title={title}
      period={period}
      provenance={provenance}
      subtitle={[
        period !== title ? period : null,
        `${integer.format(rows.length)} releases · ${integer.format(order.length)} ${nouns}`,
      ]
        .filter(Boolean)
        .join(' · ')}
      controls={controls}
      empty={!rows.length}
      focusFound={!focus || focus.dimension !== dimension || anyFocused}
      emptyText="No releases were published in this window."
      windowNote={windowText(data.window)}
      csv={() => ({
        name: `${data.id}-selected`,
        title: `${title}${period !== title ? ` — ${period}` : ''}`,
        columns,
        rows: tableRows,
      })}
      chart={chart}
      table={table}
    />
  );
}
