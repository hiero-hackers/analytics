/** Bars, lines and areas over periods or categories: the `timeseries` and `categories` kinds. */

import {
  Area,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceLine,
  XAxis,
  YAxis,
} from 'recharts';
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
import type { ChartDetail, ColumnSpec, Row, SeriesDocument, TimeseriesDocument } from '../../api';
import { dimensionOf, matches, toggle, useFocus } from '../../focus';
import { useUrlFlag, useUrlList, useUrlParam } from '../../urlState';
import { VariantTabs } from '../VariantTabs';
import { ChartShell, TABLE_CONTAINER, type ViewProps } from './ChartShell';
import { decimal, formatBucket, integer, percent, plural, shorten, windowText } from './format';

const FREQUENCY = {
  year: 'Yearly buckets · UTC',
  month: 'Monthly buckets · UTC',
  week: 'Weekly buckets · UTC',
  day: 'Daily buckets · UTC',
  snapshot: 'Point-in-time counts · UTC',
} as const;
/** Height per horizontal bar, plus room for the value axis. */
const ROW_HEIGHT = 32;
const AXIS_HEIGHT = 56;

/** A row as displayed: its category label, visible total, and (when normalised) shares. */
type ViewRow = Row & { category: string; total: number; partial?: boolean };

const share = (key: string) => `${key}__share`;

function formatDetail(value: unknown, format: ChartDetail['format']) {
  const n = Number(value);
  if (format === 'percent') return `${percent.format(n)}%`;
  return (format === 'decimal' ? decimal : integer).format(n);
}

/**
 * The exporter's comparable pair (last complete bucket vs the one before) as
 * one line per visible series; never the partial current bucket.
 */
function Comparison({
  data,
  visible,
  format,
}: {
  data: TimeseriesDocument;
  visible: SeriesDocument['series'];
  format: (value: number) => string;
}) {
  const pair = data.comparison;
  if (!pair) return null;
  const find = (bucket: string) => data.rows.find((row) => row.bucket === bucket)!;
  const [current, previous] = [find(pair.current), find(pair.previous)];
  const label = (bucket: string) => formatBucket(bucket, data.frequency);
  return (
    <div className="rounded-lg border px-3 py-2 text-xs">
      <p className="text-muted-foreground">
        {label(pair.current)} compared with {label(pair.previous)}
        {data.rows.at(-1)?.partial ? ' (the incomplete current bucket is left out)' : ''}:
      </p>
      <ul className="mt-1.5 flex flex-wrap gap-x-5 gap-y-1">
        {visible.map((series) => {
          const now = Number(current[series.key]);
          const before = Number(previous[series.key]);
          const change = now - before;
          const sign = change > 0 ? '+' : change < 0 ? '−' : '±';
          return (
            <li key={series.key} className="flex items-center gap-1.5">
              <span className="size-2.5 rounded-sm" style={{ backgroundColor: series.color }} />
              <span className="text-muted-foreground">{series.label}</span>
              <span className="font-semibold tabular-nums">{format(now)}</span>
              <span
                className="tabular-nums text-muted-foreground"
                aria-label={`${change === 0 ? 'no change' : `${change > 0 ? 'up' : 'down'} ${format(Math.abs(change))}`} from ${format(before)}`}
              >
                ({sign}
                {format(Math.abs(change))}
                {before > 0 ? `, ${sign}${percent.format(Math.abs(change / before) * 100)}%` : ''})
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function SeriesView({ data, title, period, provenance }: ViewProps<SeriesDocument>) {
  // Everything a reader changes lives in the URL, so a copied link reopens it.
  const [hidden, setHidden] = useUrlList(`${data.id}.hide`);
  const [showAll, setShowAll] = useUrlFlag(`${data.id}.all`);
  const [linkedGroup, setGroup] = useUrlParam(
    `${data.id}.group`,
    data.kind === 'categories' ? (data.group?.default ?? '') : '',
  );
  // A link naming a cohort this document no longer has opens the default one.
  const group =
    data.kind === 'categories' && data.group
      ? data.group.values.includes(linkedGroup)
        ? linkedGroup
        : data.group.default
      : undefined;
  const [focus, setFocus] = useFocus();
  const timeseries = data.kind === 'timeseries';
  const horizontal = !timeseries && data.orientation === 'horizontal';
  const categoryKey = timeseries ? 'bucket' : data.category.key;
  const groupSpec = data.kind === 'categories' ? data.group : null;
  const visible = data.series.filter((series) => !hidden.includes(series.key));
  // Categories that name repositories, people, employers or teams take part in the focus.
  const dimension = timeseries ? null : dimensionOf(data.category.key);
  const showTotal = data.stacked && data.series.length > 1;
  const format = (value: number) =>
    (data.value_format === 'integer' ? integer : decimal).format(value);

  const rows: ViewRow[] = (data.rows as Row[])
    .filter((row) => !groupSpec || row[groupSpec.key] === group)
    .map((row) => {
      const total = visible.reduce((sum, series) => sum + Number(row[series.key]), 0);
      const shares = data.normalize
        ? Object.fromEntries(
            visible.map((series) => [
              share(series.key),
              total ? (Number(row[series.key]) / total) * 100 : 0,
            ]),
          )
        : {};
      return { ...row, ...shares, category: String(row[categoryKey]), total };
    });
  // A ranking follows the series on show; otherwise the source order stands
  // (calendar order, a funnel's stages, the analysis's concentration sort).
  if (data.rank) rows.sort((a, b) => b.total - a.total);
  const limited = data.top_n !== null && rows.length > data.top_n;
  const focused = rows.find((row) => matches(focus, dimension, row.category));
  const topRows = limited && !showAll ? rows.slice(0, data.top_n ?? undefined) : rows;
  // A focused row beyond the top N still appears, so the focus is always visible.
  const chartRows = focused && !topRows.includes(focused) ? [...topRows, focused] : topRows;
  const dim = (row: ViewRow) => !!focused && row !== focused;
  const anyPartial = rows.some((row) => row.partial);
  const nouns = plural(data.category.label.replace(/ \(UTC\)$/, ''));

  const columns: ColumnSpec[] = [
    { key: categoryKey, label: data.category.label },
    ...(groupSpec ? [{ key: groupSpec.key, label: groupSpec.label }] : []),
    ...visible.map((series) => ({
      key: series.key,
      label: series.label,
      format: 'number' as const,
    })),
    ...(showTotal
      ? [{ key: 'total', label: 'Selected series total', format: 'number' as const }]
      : []),
    ...data.details.map((detail) => ({ key: detail.key, label: detail.label })),
    ...(anyPartial
      ? [{ key: 'partial', label: 'Possibly incomplete', format: 'flag' as const }]
      : []),
  ];
  // Recharts draws from these keys; the colour comes straight from each series.
  const config: ChartConfig = Object.fromEntries(
    data.series.map((series) => [series.key, { label: series.label }]),
  );
  const subtitle = [
    period !== title ? period : null,
    groupSpec ? `${groupSpec.label}: ${group}` : null,
    timeseries ? FREQUENCY[data.frequency] : `${integer.format(rows.length)} ${nouns}`,
  ]
    .filter(Boolean)
    .join(' · ');

  const valueAxis = {
    type: 'number' as const,
    allowDecimals: data.value_format === 'decimal' && !data.normalize,
    tickLine: false,
    axisLine: false,
    domain: data.normalize ? [0, 100] : undefined,
    tickFormatter: (value: number) => (data.normalize ? `${value}%` : format(Number(value))),
  };
  const categoryAxis = {
    type: 'category' as const,
    dataKey: 'category',
    tickLine: false,
    axisLine: false,
    tickFormatter: (value: string) =>
      timeseries ? formatBucket(String(value), data.frequency) : shorten(String(value)),
  };

  return (
    <ChartShell
      data={data}
      title={title}
      period={period}
      provenance={provenance}
      subtitle={subtitle}
      controls={
        <>
          {groupSpec && (
            <VariantTabs
              labels={groupSpec.values}
              active={groupSpec.values.indexOf(group ?? groupSpec.default)}
              onSelect={(index) => setGroup(groupSpec.values[index])}
              ariaLabel={`${title} ${groupSpec.label.toLowerCase()}`}
            />
          )}
          {data.series.length > 1 && (
            <div className="flex flex-wrap gap-2" role="group" aria-label="Visible series">
              {data.series.map((series) => (
                <Button
                  key={series.key}
                  size="sm"
                  variant="outline"
                  aria-pressed={!hidden.includes(series.key)}
                  disabled={visible.length === 1 && visible[0].key === series.key}
                  className={hidden.includes(series.key) ? 'opacity-50' : 'bg-card'}
                  onClick={() =>
                    setHidden(
                      hidden.includes(series.key)
                        ? hidden.filter((key) => key !== series.key)
                        : [...hidden, series.key],
                    )
                  }
                >
                  <span className="size-2.5 rounded-sm" style={{ backgroundColor: series.color }} />
                  {series.label}
                </Button>
              ))}
            </div>
          )}
          {data.kind === 'timeseries' && (
            <Comparison data={data} visible={visible} format={format} />
          )}
        </>
      }
      empty={!rows.length}
      focusFound={!dimension || !focus || focus.dimension !== dimension || !!focused}
      windowNote={windowText(data.window, anyPartial)}
      csv={() => ({
        name: `${data.id}${group ? `-${group.replace(/\W+/g, '-')}` : ''}-selected`,
        title: `${title} — ${[period !== title ? period : null, group].filter(Boolean).join(' · ') || data.unit}`,
        columns,
        rows: rows.map((row) =>
          Object.fromEntries(columns.map((column) => [column.key, row[column.key]])),
        ),
      })}
      chart={(expanded) => (
        <>
          <ChartContainer
            config={config}
            className={`${horizontal ? '' : expanded ? 'h-[min(55vh,520px)]' : 'h-[340px]'} w-full aspect-auto`}
            style={horizontal ? { height: chartRows.length * ROW_HEIGHT + AXIS_HEIGHT } : undefined}
            aria-label={`${title}. Use the arrow keys on the chart to inspect ${nouns}, or choose Data.`}
          >
            <ComposedChart
              accessibilityLayer
              data={chartRows}
              layout={horizontal ? 'vertical' : 'horizontal'}
              margin={{ top: horizontal ? 4 : 20, right: 16, left: 0, bottom: 5 }}
              barCategoryGap="25%"
            >
              <CartesianGrid vertical={horizontal} horizontal={!horizontal} strokeDasharray="3 3" />
              {horizontal ? (
                <>
                  <XAxis {...valueAxis} />
                  <YAxis {...categoryAxis} width={160} interval={0} />
                </>
              ) : (
                <>
                  <XAxis {...categoryAxis} minTickGap={24} tickMargin={12} />
                  <YAxis {...valueAxis} width={data.normalize ? 48 : 45} />
                </>
              )}
              {data.reference && (
                <ReferenceLine
                  {...(horizontal ? { x: data.reference.value } : { y: data.reference.value })}
                  stroke="var(--ink)"
                  strokeDasharray="4 4"
                  label={{
                    value: data.reference.label,
                    position: horizontal ? 'insideTopRight' : 'insideTopLeft',
                    fill: 'var(--muted)',
                    fontSize: 11,
                  }}
                />
              )}
              <ChartTooltip
                cursor={
                  data.mark === 'bar'
                    ? { fill: 'var(--raise)' }
                    : { stroke: 'var(--edge-strong)', strokeDasharray: '3 3' }
                }
                content={({ active, payload }) => {
                  const row = payload?.[0]?.payload as ViewRow | undefined;
                  if (!active || !row) return null;
                  // Dense compositions list only the segments present in the row.
                  const listed =
                    visible.length > 4
                      ? visible.filter((series) => Number(row[series.key]) !== 0)
                      : visible;
                  return (
                    <div className="grid min-w-44 gap-1.5 rounded-lg border bg-card px-3 py-2 text-xs shadow-xl">
                      <p className="font-medium">
                        {row.category}
                        {row.partial ? ' · possibly incomplete' : ''}
                      </p>
                      {listed.map((series) => (
                        <div key={series.key} className="flex items-center justify-between gap-6">
                          <span className="flex items-center gap-1.5 text-muted-foreground">
                            <span
                              className="size-2.5 shrink-0 rounded-[2px]"
                              style={{ backgroundColor: series.color }}
                            />
                            {series.label}
                          </span>
                          <span className="font-mono font-medium tabular-nums">
                            {format(Number(row[series.key]))}
                            {data.normalize
                              ? ` · ${percent.format(Number(row[share(series.key)]))}%`
                              : ''}
                          </span>
                        </div>
                      ))}
                      {showTotal && (
                        <div className="flex justify-between gap-6 border-t pt-1.5 font-semibold">
                          <span>Selected series total</span>
                          <span className="tabular-nums">{format(row.total)}</span>
                        </div>
                      )}
                      {data.details.map((detail) => (
                        <div key={detail.key} className="flex justify-between gap-6">
                          <span className="text-muted-foreground">{detail.label}</span>
                          <span className="tabular-nums">
                            {formatDetail(row[detail.key], detail.format)}
                          </span>
                        </div>
                      ))}
                    </div>
                  );
                }}
              />
              {visible.map((series, i) => {
                const key = data.normalize ? share(series.key) : series.key;
                const stackId = data.stacked ? 'stack' : undefined;
                if (data.mark === 'line') {
                  return (
                    <Line
                      key={series.key}
                      dataKey={key}
                      type="linear"
                      stroke={series.color}
                      strokeWidth={2}
                      dot={chartRows.length <= 24}
                      isAnimationActive={false}
                    />
                  );
                }
                if (data.mark === 'area') {
                  return (
                    <Area
                      key={series.key}
                      dataKey={key}
                      type="linear"
                      stackId={stackId}
                      stroke={series.color}
                      fill={series.color}
                      fillOpacity={0.4}
                      isAnimationActive={false}
                    />
                  );
                }
                const top = !data.stacked || i === visible.length - 1;
                return (
                  <Bar
                    key={series.key}
                    dataKey={key}
                    stackId={stackId}
                    fill={series.color}
                    radius={top ? (horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]) : 0}
                    maxBarSize={horizontal ? 24 : 64}
                    isAnimationActive={false}
                    className={dimension ? 'cursor-pointer' : undefined}
                    onClick={
                      dimension
                        ? (entry: { payload?: ViewRow }) =>
                            entry.payload &&
                            setFocus(toggle(focus, dimension, entry.payload.category))
                        : undefined
                    }
                  >
                    {focused &&
                      chartRows.map((row) => (
                        <Cell key={row.category} fillOpacity={dim(row) ? 0.3 : 1} />
                      ))}
                  </Bar>
                );
              })}
            </ComposedChart>
          </ChartContainer>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-muted-foreground">
              Hover or use the arrow keys to inspect values
              {data.series.length > 1 ? '; use the series buttons to compare groups' : ''}
              {dimension ? '. Click a bar to focus the dashboard on it' : ''}.
            </p>
            {limited && (
              <Button variant="outline" size="sm" onClick={() => setShowAll(!showAll)}>
                {showAll
                  ? `Show top ${data.top_n}`
                  : `Show all ${integer.format(rows.length)} ${nouns}`}
              </Button>
            )}
          </div>
        </>
      )}
      table={
        <Table containerClassName={TABLE_CONTAINER}>
          <TableHeader className="sticky top-0 bg-muted">
            <TableRow>
              {columns.map((column, i) => (
                <TableHead key={column.key} className={i ? 'text-right' : ''}>
                  {column.label}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.category} className={focused === row ? 'bg-link/10' : undefined}>
                <TableCell className="font-medium">
                  {dimension ? (
                    <Button
                      variant="link"
                      size="sm"
                      className="h-auto p-0 font-medium"
                      aria-pressed={focused === row}
                      aria-label={`Focus on ${row.category}`}
                      onClick={() => setFocus(toggle(focus, dimension, row.category))}
                    >
                      {row.category}
                    </Button>
                  ) : (
                    row.category
                  )}
                </TableCell>
                {groupSpec && <TableCell className="text-right">{group}</TableCell>}
                {visible.map((series) => (
                  <TableCell key={series.key} className="text-right tabular-nums">
                    {format(Number(row[series.key]))}
                  </TableCell>
                ))}
                {showTotal && (
                  <TableCell className="text-right font-semibold tabular-nums">
                    {format(row.total)}
                  </TableCell>
                )}
                {data.details.map((detail) => (
                  <TableCell key={detail.key} className="text-right tabular-nums">
                    {formatDetail(row[detail.key], detail.format)}
                  </TableCell>
                ))}
                {anyPartial && (
                  <TableCell className="text-right">{row.partial ? 'Yes' : '—'}</TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      }
    />
  );
}
