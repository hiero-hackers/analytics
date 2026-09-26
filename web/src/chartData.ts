import {
  API_ROOT,
  type ChartDocument,
  type EventsDocument,
  type MatrixDocument,
  type NetworkDocument,
  type Row,
  type SeriesDocument,
} from './api';

const cache = new Map<string, Promise<ChartDocument>>();
const FREQUENCIES = ['year', 'month', 'week', 'day', 'snapshot'];
/** Hex or a design token: the only colours the exporter emits. */
const COLOR = /^(#[0-9a-f]{3,8}|var\(--[\w-]+\))$/i;

const finite = (value: unknown) => typeof value === 'number' && Number.isFinite(value);
const text = (value: unknown) => typeof value === 'string';

function validRows(data: SeriesDocument): boolean {
  const integer = data.value_format === 'integer';
  const numeric = (row: Row) =>
    data.series.every(({ key }) =>
      integer ? Number.isSafeInteger(row[key]) && Number(row[key]) >= 0 : finite(row[key]),
    ) && data.details.every(({ key }) => finite(row[key]));
  if (!data.rows.every(numeric)) return false;
  if (data.kind === 'timeseries') {
    const buckets = new Set(data.rows.map((row) => row.bucket));
    const comparison = data.comparison ?? null;
    return (
      (comparison === null ||
        (buckets.has(comparison.current) && buckets.has(comparison.previous))) &&
      FREQUENCIES.includes(data.frequency) &&
      data.rows.every(
        (row, index) =>
          text(row.bucket) &&
          typeof row.partial === 'boolean' &&
          (index === 0 || data.rows[index - 1].bucket < row.bucket),
      )
    );
  }
  const group = data.group;
  if (
    group !== null &&
    !(
      text(group.key) &&
      Array.isArray(group.values) &&
      group.values.every(text) &&
      group.values.includes(group.default)
    )
  ) {
    return false;
  }
  const keys = data.rows.map((row) => {
    const category = row[data.category.key];
    const cohort = group ? row[group.key] : '';
    if (!text(category) || (group && !group.values.includes(cohort as string))) return null;
    return `${String(cohort)}\u0000${String(category)}`;
  });
  return !keys.includes(null) && new Set(keys).size === keys.length;
}

const unique = (values: unknown[]) => new Set(values).size === values.length;
const keyed = (value: unknown) =>
  !!value && text((value as { key: unknown }).key) && text((value as { label: unknown }).label);
const colored = (items: unknown) =>
  Array.isArray(items) &&
  items.every((item) => keyed(item) && COLOR.test(String((item as { color: unknown }).color)));

function validMatrix(data: MatrixDocument): boolean {
  const { scale } = data;
  const integer = data.value_format === 'integer';
  const cell = (value: unknown) =>
    value === null ||
    (finite(value) && (!integer || (Number.isSafeInteger(value) && Number(value) >= 0)));
  return (
    keyed(data.row) &&
    (data.sublabel === null || keyed(data.sublabel)) &&
    (data.total === null || keyed(data.total)) &&
    Array.isArray(data.columns) &&
    data.columns.length > 0 &&
    data.columns.every(keyed) &&
    unique(data.columns.map((column) => column.key)) &&
    text(data.value_label) &&
    !!scale &&
    finite(scale.min) &&
    finite(scale.max) &&
    scale.max > scale.min &&
    Number.isSafeInteger(scale.steps) &&
    scale.steps > 0 &&
    (data.missing === null || text(data.missing)) &&
    typeof data.avatars === 'boolean' &&
    (data.top_n === null || (Number.isSafeInteger(data.top_n) && data.top_n > 0)) &&
    Array.isArray(data.rows) &&
    data.rows.every(
      (row) =>
        text(row[data.row.key]) &&
        data.columns.every((column) => cell(row[column.key])) &&
        (data.total === null || finite(row[data.total.key])),
    ) &&
    unique(data.rows.map((row) => row[data.row.key]))
  );
}

function validNetwork(data: NetworkDocument): boolean {
  const count = (value: unknown) => Number.isSafeInteger(value) && Number(value) >= 0;
  if (!(text(data.member_label) && colored(data.categories) && Array.isArray(data.nodes))) {
    return false;
  }
  const categories = new Set(data.categories.map((category) => category.key));
  const ids = data.nodes.map((node) => node.id);
  const known = new Set(ids);
  return (
    data.nodes.every(
      (node) =>
        text(node.id) &&
        count(node.active) &&
        count(node.total) &&
        categories.has(node.category) &&
        finite(node.x) &&
        finite(node.y),
    ) &&
    unique(ids) &&
    Array.isArray(data.edges) &&
    data.edges.every(
      (edge) =>
        known.has(edge.source) &&
        known.has(edge.target) &&
        edge.source !== edge.target &&
        count(edge.shared),
    ) &&
    unique(data.edges.map((edge) => [edge.source, edge.target].sort().join('\u0000')))
  );
}

function validEvents(data: EventsDocument): boolean {
  if (!(keyed(data.category) && keyed(data.label) && colored(data.types))) return false;
  const types = new Set(data.types.map((type) => type.key));
  const categories = new Set(data.categories);
  return (
    Array.isArray(data.categories) &&
    data.categories.every(text) &&
    unique(data.categories) &&
    Array.isArray(data.rows) &&
    data.rows.every(
      (row) =>
        categories.has(row[data.category.key] as string) &&
        text(row.time) &&
        !Number.isNaN(Date.parse(String(row.time))) &&
        text(row[data.label.key]) &&
        types.has(row.type as string),
    )
  );
}

function validSeries(data: SeriesDocument): boolean {
  return (
    ['bar', 'line', 'area'].includes(data.mark) &&
    ['vertical', 'horizontal'].includes(data.orientation) &&
    ['integer', 'decimal'].includes(data.value_format) &&
    typeof data.stacked === 'boolean' &&
    typeof data.normalize === 'boolean' &&
    typeof data.rank === 'boolean' &&
    (data.top_n === null || (Number.isSafeInteger(data.top_n) && data.top_n > 0)) &&
    (data.reference === null || (finite(data.reference?.value) && text(data.reference.label))) &&
    !!data.category &&
    text(data.category.key) &&
    text(data.category.label) &&
    Array.isArray(data.series) &&
    data.series.length > 0 &&
    data.series.every((s) => text(s.key) && text(s.label) && COLOR.test(String(s.color))) &&
    new Set(data.series.map((s) => s.key)).size === data.series.length &&
    Array.isArray(data.details) &&
    data.details.every((d) => text(d.key) && ['number', 'decimal', 'percent'].includes(d.format)) &&
    Array.isArray(data.rows) &&
    validRows(data)
  );
}

/** Reject malformed documents instead of quietly rendering misleading charts. */
export function validateChartDocument(value: unknown): ChartDocument {
  const data = value as ChartDocument;
  const meta =
    !!data &&
    data.schema_version === 1 &&
    text(data.unit) &&
    text(data.population) &&
    (data.note === undefined || text(data.note)) &&
    Array.isArray(data.dimensions) &&
    !!data.window;
  const valid =
    meta &&
    (data.kind === 'matrix'
      ? validMatrix(data)
      : data.kind === 'network'
        ? validNetwork(data)
        : data.kind === 'events'
          ? validEvents(data)
          : (data.kind === 'timeseries' || data.kind === 'categories') && validSeries(data));
  if (!valid) {
    throw new Error('The chart dataset is invalid.');
  }
  return data;
}

/** Share requests between cards; failed requests are evicted so Retry really retries. */
export function fetchChartDocument(path: string): Promise<ChartDocument> {
  const cached = cache.get(path);
  if (cached) return cached;
  const request = fetch(`${API_ROOT}/${path}`)
    .then(async (response) => {
      if (!response.ok) throw new Error(`Chart data: HTTP ${response.status}`);
      return validateChartDocument(await response.json());
    })
    .catch((error: unknown) => {
      cache.delete(path);
      throw error;
    });
  cache.set(path, request);
  return request;
}
