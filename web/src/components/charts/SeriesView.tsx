/** Bars, lines and areas over periods or categories: the `timeseries` and `categories` kinds. */

import {
  Area,
  AreaChart,
  Bar,
  Brush,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceLine,
  XAxis,
  YAxis,
} from 'recharts';
import { ChartAreaIcon, ChartColumnIcon, ChartLineIcon } from 'lucide-react';
import { cn } from 'cn';
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
import { Funnel, Meter } from './Composition';
import {
  decimal,
  formatBucket,
  integer,
  percent,
  plural,
  shorten,
  spanOf,
  windowText,
} from './format';

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
/** Fit the category axis to its longest shortened label, leaving the rest to the bars. */
const labelWidth = (labels: string[]) =>
  Math.min(
    184,
    Math.max(64, Math.ceil(Math.max(0, ...labels.map((l) => shorten(l).length)) * 7.2) + 12),
  );

/** A row as displayed: its category label, visible total, and (when normalised) shares. */
type ViewRow = Row & { category: string; total: number; partial?: boolean };

const share = (key: string) => `${key}__share`;
/** The running total up the stack to (and including) a series, drawn by cumulative lines. */
const cumulative = (key: string) => `${key}__cumulative`;

/** Series longer than this get an overview strip to brush a span of buckets. */
const OVERVIEW_MIN = 24;
const PRESETS = ['all', '24', '12'];

function formatDetail(value: unknown, format: ChartDetail['format']) {
  const n = Number(value);
  if (format === 'percent') return `${percent.format(n)}%`;
  return (format === 'decimal' ? decimal : integer).format(n);
}

/** Last complete bucket vs the one before, per visible series; never the partial current bucket. */
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
    <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1.5 rounded-lg bg-muted/60 px-3 py-2 text-xs">
      <p className="font-medium text-foreground">
        {label(pair.current)} compared with {label(pair.previous)}
        <span className="font-normal text-muted-foreground">
          {data.rows.at(-1)?.partial ? ' (the incomplete current bucket is left out)' : ''}
        </span>
      </p>
      <ul className="flex flex-wrap gap-x-5 gap-y-1">
        {visible.map((series) => {
          const now = Number(current[series.key]);
          const before = Number(previous[series.key]);
          const change = now - before;
          const sign = change > 0 ? '+' : change < 0 ? '−' : '±';
          return (
            <li key={series.key} className="flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className="size-2 rounded-full"
                style={{ backgroundColor: series.color }}
              />
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

export function SeriesView({
  data,
  title,
  period,
  provenance,
  roomy = false,
}: ViewProps<SeriesDocument>) {
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
  const [scale, setScale] = useUrlParam(`${data.id}.scale`, 'counts');
  const canChooseScale = data.stacked && data.series.length > 1 && !data.normalize;
  const normalized = data.normalize || (canChooseScale && scale === 'share');

  const [linkedMark, setMark] = useUrlParam(`${data.id}.mark`, data.mark);
  const mark = timeseries && ['bar', 'line', 'area'].includes(linkedMark) ? linkedMark : data.mark;
  const composition = mark === 'meter' || mark === 'funnel';
  // A span selects existing buckets only; people are never re-aggregated across them.
  const [range, setRange] = useUrlParam(`${data.id}.range`, 'all');
  const buckets = timeseries ? data.rows.map((row) => row.bucket) : [];
  const [spanStart, spanEnd] = timeseries ? spanOf(range, buckets) : [0, data.rows.length - 1];
  const spanned = timeseries && (spanStart > 0 || spanEnd < data.rows.length - 1);
  const preset = PRESETS.indexOf(spanned ? range : 'all');
  const selectedRows = spanned ? data.rows.slice(spanStart, spanEnd + 1) : data.rows;
  const overview = timeseries && data.rows.length > OVERVIEW_MIN;

  const horizontal = !timeseries && data.orientation === 'horizontal';
  const categoryKey = timeseries ? 'bucket' : data.category.key;
  const groupSpec = data.kind === 'categories' ? data.group : null;
  const visible = data.series.filter((series) => !hidden.includes(series.key));
  // Categories that name repositories, people, employers or teams take part in the focus.
  const dimension = timeseries ? null : dimensionOf(data.category.key);
  const showTotal = data.stacked && data.series.length > 1;
  // Lines don't stack, so a stacked document's lines default to cumulative (running total
  // up the stack). This sums across series, never across periods.
  const [lineMode, setLineMode] = useUrlParam(`${data.id}.lines`, 'cumulative');
  const canStackLines = mark === 'line' && data.stacked && visible.length > 1;
  const stackedLines = canStackLines && lineMode !== 'separate';
  const format = (value: number) =>
    (data.value_format === 'integer' ? integer : decimal).format(value);

  const rows: ViewRow[] = (selectedRows as Row[])
    .filter((row) => !groupSpec || row[groupSpec.key] === group)
    .map((row) => {
      const total = visible.reduce((sum, series) => sum + Number(row[series.key]), 0);
      const shares = normalized
        ? Object.fromEntries(
            visible.map((series) => [
              share(series.key),
              total ? (Number(row[series.key]) / total) * 100 : 0,
            ]),
          )
        : {};
      let running = 0;
      const stacked = stackedLines
        ? Object.fromEntries(
            visible.map((series) => {
              running += Number(normalized ? shares[share(series.key)] : row[series.key]);
              return [cumulative(series.key), running];
            }),
          )
        : {};
      return { ...row, ...shares, ...stacked, category: String(row[categoryKey]), total };
    });
  // A ranking follows the series on show; otherwise the source order stands
  // (calendar order, a funnel's stages, the analysis's concentration sort).
  if (data.rank) rows.sort((a, b) => b.total - a.total);
  // A lead chart has the height of two stacked peers, so it ranks more rows.
  const topN = data.top_n !== null && roomy ? Math.ceil(data.top_n * 1.5) : data.top_n;
  const limited = topN !== null && rows.length > topN;
  const focused = rows.find((row) => matches(focus, dimension, row.category));
  const topRows = limited && !showAll ? rows.slice(0, topN ?? undefined) : rows;
  // A focused row beyond the top N still appears, so the focus is always visible.
  const chartRows = focused && !topRows.includes(focused) ? [...topRows, focused] : topRows;
  const dim = (row: ViewRow) => !!focused && row !== focused;
  const anyPartial = rows.some((row) => row.partial);
  // The overview always spans every bucket, drawn as the visible series' total.
  const overviewRows = overview
    ? data.rows.map((row) => ({
        bucket: row.bucket,
        total: visible.reduce((sum, series) => sum + Number(row[series.key]), 0),
      }))
    : [];
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
  // Labels only: each mark takes its colour straight from its series.
  const config: ChartConfig = Object.fromEntries(
    data.series.map((series) => [series.key, { label: series.label }]),
  );
  const subtitle = [
    period !== title ? period : null,
    groupSpec ? `${groupSpec.label}: ${group}` : null,
    timeseries
      ? FREQUENCY[data.frequency]
      : // A meter's headline already gives the total; counting its statuses says nothing.
        mark === 'meter'
        ? null
        : `${integer.format(rows.length)} ${nouns}`,
  ]
    .filter(Boolean)
    .join(' · ');

  const valueAxis = {
    type: 'number' as const,
    allowDecimals: data.value_format === 'decimal' && !normalized,
    tickLine: false,
    axisLine: false,
    domain: normalized ? [0, 100] : data.value_max ? [0, data.value_max] : undefined,
    // Even steps across a bounded scale: 0, 2, … 10 rather than 0, 3, … 9, 10.
    tickCount: data.value_max && !normalized ? 6 : undefined,
    tickFormatter: (value: number) => (normalized ? `${value}%` : format(Number(value))),
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
      toolbar={
        <>
          {timeseries && (
            <VariantTabs
              appearance="segmented"
              labels={['Bars', 'Line', 'Area']}
              icons={[
                <ChartColumnIcon key="bar" />,
                <ChartLineIcon key="line" />,
                <ChartAreaIcon key="area" />,
              ]}
              active={['bar', 'line', 'area'].indexOf(mark)}
              onSelect={(index) => setMark(['bar', 'line', 'area'][index])}
              ariaLabel={`${title} chart style`}
            />
          )}
          {canStackLines && (
            <VariantTabs
              appearance="segmented"
              labels={['Cumulative', 'Separate lines']}
              active={stackedLines ? 0 : 1}
              onSelect={(index) => setLineMode(index ? 'separate' : 'cumulative')}
              ariaLabel={`${title} line stacking`}
            />
          )}
          {canChooseScale && (
            <VariantTabs
              appearance="segmented"
              labels={['Counts', 'Share (%)']}
              active={normalized ? 1 : 0}
              onSelect={(index) => setScale(index ? 'share' : 'counts')}
              ariaLabel={`${title} scale`}
            />
          )}
          {timeseries && data.rows.length > 12 && (
            <VariantTabs
              appearance="segmented"
              labels={['All periods', 'Latest 24', 'Latest 12']}
              active={preset}
              onSelect={(index) => setRange(PRESETS[index])}
              ariaLabel={`${title} visible periods`}
            />
          )}
          {groupSpec && (
            <VariantTabs
              appearance="segmented"
              labels={groupSpec.values}
              active={groupSpec.values.indexOf(group ?? groupSpec.default)}
              onSelect={(index) => setGroup(groupSpec.values[index])}
              ariaLabel={`${title} ${groupSpec.label.toLowerCase()}`}
            />
          )}
          {spanned && (
            <span className="text-xs text-muted-foreground" aria-live="polite">
              {formatBucket(buckets[spanStart], data.frequency)} –{' '}
              {formatBucket(buckets[spanEnd], data.frequency)} ({rows.length} of {data.rows.length}{' '}
              buckets)
              {preset < 0 && (
                <Button
                  variant="link"
                  size="sm"
                  className="ml-2 h-auto p-0 text-xs"
                  onClick={() => setRange('all')}
                >
                  Reset span
                </Button>
              )}
            </span>
          )}
        </>
      }
      controls={
        (data.series.length > 1 || data.kind === 'timeseries') && (
          <div className="space-y-2.5">
            {data.series.length > 1 && (
              // The legend doubles as the series switch.
              <div
                className="flex flex-wrap gap-x-1 gap-y-1"
                role="group"
                aria-label="Visible series"
              >
                {data.series.map((series) => {
                  const off = hidden.includes(series.key);
                  return (
                    <Button
                      key={series.key}
                      size="sm"
                      variant="ghost"
                      aria-pressed={!off}
                      disabled={visible.length === 1 && visible[0].key === series.key}
                      className={cn(
                        'h-7 gap-1.5 rounded-full px-2.5 text-xs font-medium',
                        off ? 'text-muted-foreground line-through decoration-1' : 'text-foreground',
                      )}
                      onClick={() =>
                        setHidden(
                          off
                            ? hidden.filter((key) => key !== series.key)
                            : [...hidden, series.key],
                        )
                      }
                    >
                      <span
                        aria-hidden="true"
                        className={cn(
                          'size-2.5 rounded-full transition-opacity',
                          off && 'opacity-30',
                        )}
                        style={{ backgroundColor: series.color }}
                      />
                      {series.label}
                    </Button>
                  );
                })}
              </div>
            )}
            {data.kind === 'timeseries' && (
              <Comparison data={data} visible={visible} format={format} />
            )}
          </div>
        )
      }
      empty={!rows.length}
      focusFound={!dimension || !focus || focus.dimension !== dimension || !!focused}
      windowNote={[
        windowText(data.window, anyPartial),
        normalized
          ? 'Each row shows the percentage of its visible series; the data table and CSV retain the original counts.'
          : null,
        stackedLines
          ? `Cumulative lines: each line adds its series to the ones below it (${visible
              .map((series) => series.label)
              .join(
                ' → ',
              )}), so the top line is the visible total. The tooltip, data table and CSV give each series on its own.`
          : null,
      ]
        .filter(Boolean)
        .join(' ')}
      csv={() => ({
        name: `${data.id}${group ? `-${group.replace(/\W+/g, '-')}` : ''}-selected`,
        title: `${title} — ${[period !== title ? period : null, group].filter(Boolean).join(' · ') || data.unit}`,
        columns,
        rows: rows.map((row) =>
          Object.fromEntries(columns.map((column) => [column.key, row[column.key]])),
        ),
      })}
      chart={(expanded) =>
        composition ? (
          mark === 'meter' ? (
            <Meter rows={rows} series={visible[0]} unit={data.unit} format={format} />
          ) : (
            <Funnel rows={rows} series={visible[0]} format={format} />
          )
        ) : (
          <>
            <ChartContainer
              config={config}
              className={`${horizontal ? '' : expanded ? 'h-[min(55vh,520px)]' : 'h-[340px]'} w-full aspect-auto`}
              style={
                horizontal
                  ? {
                      height:
                        chartRows.length * ROW_HEIGHT + AXIS_HEIGHT + (data.reference ? 16 : 0),
                    }
                  : undefined
              }
              aria-label={`${title}. Use the arrow keys on the chart to inspect ${nouns}, or choose Data.`}
            >
              <ComposedChart
                accessibilityLayer
                data={chartRows}
                layout={horizontal ? 'vertical' : 'horizontal'}
                // A reference line's label needs its own band above the first bar.
                margin={{
                  top: horizontal && !data.reference ? 4 : 20,
                  right: 16,
                  left: 0,
                  bottom: 5,
                }}
                barCategoryGap="25%"
              >
                <CartesianGrid
                  vertical={horizontal}
                  horizontal={!horizontal}
                  strokeDasharray="3 3"
                />
                {horizontal ? (
                  <>
                    <XAxis {...valueAxis} />
                    <YAxis
                      {...categoryAxis}
                      width={labelWidth(chartRows.map((row) => row.category))}
                      interval={0}
                    />
                  </>
                ) : (
                  <>
                    <XAxis {...categoryAxis} minTickGap={24} tickMargin={12} />
                    <YAxis {...valueAxis} width={normalized ? 48 : 45} />
                  </>
                )}
                {data.reference && (
                  <ReferenceLine
                    {...(horizontal ? { x: data.reference.value } : { y: data.reference.value })}
                    stroke="var(--ink)"
                    strokeDasharray="4 4"
                    label={{
                      value: data.reference.label,
                      position: horizontal ? 'top' : 'insideTopLeft',
                      fill: 'var(--muted)',
                      fontSize: 11,
                    }}
                  />
                )}
                <ChartTooltip
                  cursor={
                    mark === 'bar'
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
                              {normalized
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
                  const key = normalized ? share(series.key) : series.key;
                  const stackId = data.stacked ? 'stack' : undefined;
                  if (mark === 'line') {
                    return (
                      <Line
                        key={series.key}
                        dataKey={stackedLines ? cumulative(series.key) : key}
                        type="linear"
                        stroke={series.color}
                        strokeWidth={2}
                        dot={chartRows.length <= 24}
                        isAnimationActive={false}
                      />
                    );
                  }
                  if (mark === 'area') {
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
            {overview && (
              <div className="rounded-lg border px-2 pt-2">
                <p className="px-1 text-xs text-muted-foreground">
                  Overview of all {data.rows.length} buckets · drag the handles, or focus one and
                  use the arrow keys, to choose the span shown above
                </p>
                <ChartContainer config={config} className="aspect-auto h-[76px] w-full">
                  <ComposedChart
                    data={overviewRows}
                    margin={{ top: 4, right: 16, left: 16, bottom: 4 }}
                  >
                    <Brush
                      dataKey="bucket"
                      height={64}
                      startIndex={spanStart}
                      endIndex={spanEnd}
                      travellerWidth={10}
                      stroke="var(--link)"
                      fill="var(--surface)"
                      ariaLabel={`${title}: choose the visible span`}
                      tickFormatter={(value) => formatBucket(String(value), data.frequency)}
                      onChange={({ startIndex, endIndex }) => {
                        if (startIndex === undefined || endIndex === undefined) return;
                        setRange(
                          startIndex === 0 && endIndex === buckets.length - 1
                            ? 'all'
                            : `${buckets[startIndex]}~${buckets[endIndex]}`,
                        );
                      }}
                    >
                      <AreaChart data={overviewRows}>
                        <Area
                          dataKey="total"
                          type="linear"
                          stroke="var(--muted)"
                          fill="var(--muted)"
                          fillOpacity={0.2}
                          isAnimationActive={false}
                        />
                      </AreaChart>
                    </Brush>
                  </ComposedChart>
                </ChartContainer>
              </div>
            )}
            <div className="flex flex-wrap items-center justify-between gap-2">
              {/* Hover and arrow keys are announced by the chart's label; only clicking is spelled out. */}
              <p className="text-xs text-muted-foreground">
                {dimension ? 'Click a bar to focus the dashboard on it.' : ''}
              </p>
              {limited && (
                <Button variant="outline" size="sm" onClick={() => setShowAll(!showAll)}>
                  {showAll
                    ? `Show top ${topN}`
                    : `Show all ${integer.format(rows.length)} ${nouns}`}
                </Button>
              )}
            </div>
          </>
        )
      }
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
