/**
 * Typed client for the analytics data API (outputs/data/api/v1).
 *
 * The shapes here mirror what `export/data_api.py` emits and are the only
 * coupling between this app and the Python side: the app renders whatever the
 * manifest lists, so new sections and orgs appear without frontend changes.
 */

/**
 * Mirrors `dashboard_spec.COLUMN_FORMATS` in Python — the single source of
 * truth for the valid set. Keep the two lists in sync; a mismatch is a
 * compile-time error here and a test failure on the Python side.
 */
export type ColumnFormat =
  | 'hip'
  | 'date'
  | 'link'
  | 'evidence'
  | 'status'
  | 'flag'
  | 'presence'
  | 'number'
  | 'percent'
  | 'staleness';

export interface ColumnSpec {
  key: string;
  label: string;
  /**
   * Optional display format, rendered by `components/FormattedCell`. The
   * valid set is declared once in Python (`dashboard_spec.COLUMN_FORMATS`)
   * and enforced there, so a spec typo fails a test rather than shipping as
   * an unformatted column.
   */
  format?: ColumnFormat;
}

export interface SectionRef {
  id: string;
  macro: string;
  title: string;
  row_count: number;
  path: string;
  /**
   * Set when this section is a role variant another card now renders as a tab.
   * Its document still exists and still resolves — `v1` is additive-only, so a
   * merged card may not withdraw an id — but the dashboard reads its rows from
   * the absorbing section's `variants` rather than fetching it twice.
   */
  absorbed_by?: string;
}

/** One drawn series; `color` is a hex value or a `var(--token)` reference. */
export interface ChartSeries {
  key: string;
  label: string;
  color: string;
}

/** A value shown beside the series in the tooltip and table, never drawn. */
export interface ChartDetail {
  key: string;
  label: string;
  format: 'number' | 'decimal' | 'percent';
}

/** Fields every interactive chart document shares (see export/chart_data.py). */
export interface ChartDocumentMeta {
  schema_version: 1;
  id: string;
  org: string;
  source: string;
  metric: string;
  unit: string;
  /** Who is counted and how; always shown, independently of the chart note. */
  population: string;
  /** What the rows can be sliced by; the UI offers nothing else. */
  dimensions: string[];
  note?: string;
  methodology?: string[];
  generated_at?: string;
  stale?: boolean;
}

/** `trailing`: the `days` before `end`; `all`: every event; `snapshot`: the state at `end`. */
export interface ChartWindow {
  kind: 'snapshot' | 'all' | 'trailing';
  days: number | null;
  end: string | null;
}

/** Bars, lines and areas over periods or categories. */
interface ChartDocumentBase extends ChartDocumentMeta {
  /** `meter` (statuses, headline first) and `funnel` (stages in order) are single-series. */
  mark: 'bar' | 'line' | 'area' | 'meter' | 'funnel';
  stacked: boolean;
  /** Draw each row as shares of its visible total; the table keeps counts. */
  normalize: boolean;
  orientation: 'vertical' | 'horizontal';
  value_format: 'integer' | 'decimal';
  /** Re-rank rows by the series on show, rather than keeping the source order. */
  rank: boolean;
  /** Rows charted before "Show all"; the data view always lists every row. */
  top_n: number | null;
  reference: { value: number; label: string } | null;
  /** A bounded scale's ceiling (e.g. 10 for a 0–10 score). */
  value_max?: number | null;
  category: { key: string; label: string };
  series: ChartSeries[];
  details: ChartDetail[];
}

export interface TimeseriesDocument extends ChartDocumentBase {
  kind: 'timeseries';
  mark: 'bar' | 'line' | 'area';
  /** `snapshot`: point-in-time measurements on the listed dates, never gap-filled. */
  frequency: 'year' | 'month' | 'week' | 'day' | 'snapshot';
  timezone: 'UTC';
  /** The last complete bucket and the one before it; null when no fair pair exists. */
  comparison: { current: string; previous: string } | null;
  group: null;
  window: { kind: 'calendar'; first: string | null; last: string | null };
  rows: (Row & { bucket: string; partial: boolean })[];
}

export interface CategoriesDocument extends ChartDocumentBase {
  kind: 'categories';
  /** Rows split by a reader-selected value (e.g. a funnel cohort); never combined. */
  group: { key: string; label: string; default: string; values: string[] } | null;
  window: ChartWindow;
  rows: Row[];
}

/** A heatmap: one row per entity, one value per column, on an explicit linear scale. */
export interface MatrixDocument extends ChartDocumentMeta {
  kind: 'matrix';
  row: { key: string; label: string };
  sublabel: { key: string; label: string } | null;
  /** A per-row summary (e.g. the six-month score), shown but never coloured. */
  total: { key: string; label: string } | null;
  columns: { key: string; label: string }[];
  value_label: string;
  /** Linear from `min` to `max`, drawn in `steps` equal shades. */
  scale: { min: number; max: number; steps: number };
  /** What a null cell means (e.g. "Not scored"); null when every cell has a value. */
  missing: string | null;
  /** Row keys are GitHub logins: show avatars and profile links. */
  avatars: boolean;
  top_n: number | null;
  value_format: 'integer' | 'decimal';
  window: ChartWindow;
  rows: Row[];
}

export interface NetworkNode {
  id: string;
  /** Members active in the repository recently: the bubble size. */
  active: number;
  total: number;
  category: string;
  /** Precomputed layout position (y up). */
  x: number;
  y: number;
}

/** Repositories linked by shared members, with a precomputed layout. */
export interface NetworkDocument extends ChartDocumentMeta {
  kind: 'network';
  member_label: string;
  categories: ChartSeries[];
  window: ChartWindow;
  nodes: NetworkNode[];
  edges: { source: string; target: string; shared: number }[];
}

/** Individual timestamped events (releases) in a trailing window. */
export interface EventsDocument extends ChartDocumentMeta {
  kind: 'events';
  category: { key: string; label: string };
  label: { key: string; label: string };
  types: ChartSeries[];
  /** Row order for the timeline: busiest first. */
  categories: string[];
  window: ChartWindow;
  /** Each has the category key, `time` (ISO UTC), the label key, and `type`. */
  rows: Row[];
}

export type SeriesDocument = TimeseriesDocument | CategoriesDocument;
export type ChartDocument = SeriesDocument | MatrixDocument | NetworkDocument | EventsDocument;

export interface ChartVariant {
  interactive?: { kind: ChartDocument['kind']; path: string };
  label: string;
  /** The variant's PNG, which always exists (v1 lists no variant without one). The
   *  dashboard keys the variant by it and draws from `interactive` instead. */
  file: string;
  /**
   * This tab's own "how to read this" and derivation steps. A chart's tabs show
   * different populations (maintainers / committers) or different spans, so the
   * text has to follow the tab; the chart-level fields below remain the
   * fallback for a tab with no entry of its own.
   */
  note?: string;
  methodology?: string[];
}

export interface ChartSpec {
  title: string;
  variants: ChartVariant[];
  note?: string;
  methodology?: string[];
  /** Many bars: full row with a horizontal scroll box. */
  wide?: boolean;
  /** Wide aspect, few bars: full row, scaled to fit (no scroll box). */
  full_row?: boolean;
}

export interface ChartDownload {
  name: string;
  path: string;
  generated_at?: string;
}

export interface ChartSection {
  id: string;
  macro: string;
  title: string;
  description: string;
  /** Renders inside this named table group (above its tables) instead of the Charts block. */
  group?: string;
  slideshow?: boolean;
  charts: ChartSpec[];
  /** A companion CSV copied into the API tree, offered as a download. */
  download?: ChartDownload;
  /**
   * Companion CSVs per chart-variant label, for a card whose tabs show
   * different populations. The card offers the one matching its shared variant
   * axis and hides the button where that tab has none — a single download here
   * would hand a reader on the Committers tab the maintainer table.
   */
  downloads?: Record<string, ChartDownload>;
}

/** A bespoke view the manifest lists by reference, like sections. */
export interface ViewRef {
  id: string;
  macro: string;
  kind: string;
  title: string;
  path: string;
}

export interface MatrixCell {
  key: string;
  merged: number;
  open: number;
}

/** The trailing parity note of a matrix row (e.g. which SDKs lack PRs). */
export interface GapNote {
  kind: 'complete' | 'none' | 'partial';
  text: string;
  items?: string[];
}

export interface MatrixRow {
  key: number;
  label: string;
  sublabel: string;
  status: string;
  cells: MatrixCell[];
  note: GapNote;
}

/** A generic entity x category matrix (today: HIP implementation coverage). */
export interface MatrixView {
  id: string;
  kind: 'matrix';
  macro: string;
  /** The named section group this view renders under. */
  group?: string;
  title: string;
  description: string;
  badge: string;
  source: string;
  row_header: string;
  note_header: string;
  bands: { label: string; span: number }[];
  columns: { key: string; label: string; band: string }[];
  rows: MatrixRow[];
  ramp: string[];
  ramp_ceilings: number[];
  filters: string[];
  evidence_section: string;
  generated_at?: string;
  stale?: boolean;
}

export interface BoardItem {
  key: number;
  label: string;
  title: string;
  status: string;
}

/** Entities placed in lifecycle columns (today: the HIP governance board). */
export interface BoardView {
  id: string;
  kind: 'board';
  macro: string;
  /** The named section group this view renders under. */
  group?: string;
  title: string;
  description: string;
  badge: string;
  source: string;
  columns: { title: string; items: BoardItem[] }[];
  target_view: string;
  generated_at?: string;
  stale?: boolean;
}

export type ViewDoc = MatrixView | BoardView;

export interface MetricTile {
  label: string;
  value: string | number;
  /** How to read the number, and the steps that produced it. */
  note?: string;
  methodology?: string[];
}

export interface OrgEntry {
  sections: SectionRef[];
  chart_sections: ChartSection[];
  views?: ViewRef[];
  metrics: Record<string, MetricTile[]>;
  /** The repository and contributor detail views' indexes; absent when not produced. */
  entities?: EntityRefs;
}

/** Where an org's entity indexes live, and how many entities each lists. */
export interface EntityRefs {
  repositories?: { path: string; count: number };
  contributors?: { path: string; count: number };
}

export interface Glossary {
  title: string;
  terms: { term: string; definition: string }[];
  note?: string;
  /** "definitions" (default): term/definition grid. "notes": lead-in + prose list. */
  layout?: string;
}

export interface Manifest {
  version: string;
  generated_at: string;
  /** Each macro's explainer, keyed by macro name — one per tab. */
  macro_glossaries?: Record<string, Glossary>;
  /** Sub-tab macros: macro name -> umbrella tab name (e.g. "Teams & TSC" -> "Governance"). */
  macro_parents?: Record<string, string>;
  /** Family display order for tabs; macros not listed keep their derived order. */
  macro_order?: string[];
  /** Why a tab may be empty for an org — shown in place of a blank tab. */
  macro_absent_notes?: Record<string, string>;
  /** Each tab's one-line purpose, shown under its title. */
  macro_summaries?: Record<string, string>;
  /** Macro name -> ordered section-group names; each tab renders as this sequence. */
  group_order?: Record<string, string[]>;
  /** Display labels for rolling periods ("30d" -> "30 days"). */
  period_labels?: Record<string, string>;
  /** Where the footer sends a reader who spots something wrong. */
  issues_url?: string;
  /** Show the work-in-progress banner. Absent means show — an older cached
   *  manifest must fail toward warning too long, never hiding too early. */
  wip?: boolean;
  provenance: { git_sha: string | null; data_as_of: string | null };
  orgs: Record<string, OrgEntry>;
}

export type Row = Record<string, unknown>;

/**
 * One role variant of a tabbed table section. Carries a full table of its own:
 * the count column is named for the role it counts, so the variants differ in
 * shape and not only in labels.
 */
export interface SectionVariant {
  id: string;
  label: string;
  title: string;
  description: string;
  source: string;
  columns: ColumnSpec[];
  rows: Row[];
  row_count: number;
  action?: { url: string; label: string };
  generated_at?: string;
  stale?: boolean;
  periods?: Record<string, Row[]>;
}

export interface SectionDoc {
  id: string;
  title: string;
  description: string;
  group: string;
  macro: string;
  source: string;
  columns: ColumnSpec[];
  rows: Row[];
  row_count: number;
  action?: { url: string; label: string };
  generated_at?: string;
  stale?: boolean;
  periods?: Record<string, Row[]>;
  /**
   * Role tabs. The first variant is also hoisted to the fields above, so a
   * consumer that predates this field reads the same table it always did.
   * Present only when more than one variant was produced.
   */
  variants?: SectionVariant[];
}

/** A table shaped like a section: all-time rows, plus period variants (export/entity_views.py). */
export type TableDoc = Omit<SectionDoc, 'group' | 'macro'>;

/** The five tracked action counts, their total and the entity's own extra count. */
export interface EntityCounts {
  prs_opened: number;
  reviews_given: number;
  merges_done: number;
  issues_opened: number;
  labels_applied: number;
  total_actions: number;
  /** Repositories only: distinct people with a tracked action in the window. */
  active_contributors?: number;
  /** Contributors only: repositories with a tracked action by them in the window. */
  repos_touched?: number;
}

export type WorkFamily =
  'building_and_fixing' | 'reviewing_and_guiding' | 'organizing_and_answering';

/** The windows a detail document counts: Week, 1 month, 1 year (their start dates) and all time. */
export interface EntityWindow {
  /** When the analysis ran; every window ends here. */
  end: string | null;
  /** The latest tracked event in the organisation's data. */
  data_through?: string | null;
  periods: { key: string; label: string; days: number | null; start?: string | null }[];
}

interface EntityDocumentBase {
  schema_version: 1;
  org: string;
  id: string;
  generated_at?: string;
  stale?: boolean;
  /** What the counts cover, and what they do not. */
  scope: string;
  population: string;
  methodology: string[];
  limits: string[];
  source: string[];
  window: EntityWindow;
  github_url: string;
  first_active: string | null;
  last_active: string | null;
  /** Counts keyed by window: `all`, `365d`, `30d`, `7d`; a quiet window is all zeros. */
  summary: Record<string, EntityCounts>;
  mix: Record<string, Record<WorkFamily, { count: number; share: number }>>;
  /** Tracked actions per month, as a chart document; null without any. */
  trend: TimeseriesDocument | null;
}

/** An optional per-repository table joined into a repository's view. */
export interface RelatedSection {
  id: string;
  title: string;
  source: string[];
  /** The dashboard sections these figures come from, each a jump target (`#tab=…&widget=…`). */
  links?: { macro: string; id: string; title: string }[];
  fields: { key: string; label: string; value: unknown; format?: ColumnFormat }[];
  generated_at?: string;
  stale?: boolean;
  list?: {
    title: string;
    source: string;
    columns: ColumnSpec[];
    rows: Row[];
    generated_at?: string;
    stale?: boolean;
  };
}

export interface RepositoryDocument extends EntityDocumentBase {
  kind: 'repository';
  name: string;
  full_name: string;
  contributors: TableDoc;
  related: RelatedSection[];
  /** Titles of the optional sections whose tables this run did not produce. */
  unavailable: string[];
}

export interface ContributorDocument extends EntityDocumentBase {
  kind: 'contributor';
  login: string;
  repositories: TableDoc;
}

export type EntityDocument = RepositoryDocument | ContributorDocument;

export interface EntityIndexRow {
  id: string;
  /** Repositories: the bare and `owner/repo` names. */
  name?: string;
  full_name?: string;
  /** Contributors: the GitHub login as GitHub spells it. */
  login?: string;
  total_actions: number;
  last_active: string | null;
}

export interface EntityIndex {
  schema_version: 1;
  kind: 'repositories-index' | 'contributors-index';
  org: string;
  generated_at?: string;
  stale?: boolean;
  /** Where a row's document lives: `{id}` is replaced by its id. */
  detail_path: string;
  window: EntityWindow;
  rows: EntityIndexRow[];
}

/** Deploy-relative roots: the app and the API ship together. */
const BASE = import.meta.env.BASE_URL;
export const API_ROOT = `${BASE}data/api/v1`;

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url}: HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export const fetchManifest = (): Promise<Manifest> =>
  getJson<Manifest>(`${API_ROOT}/manifest.json`);

export const fetchSection = (ref: SectionRef): Promise<SectionDoc> =>
  getJson<SectionDoc>(`${API_ROOT}/${ref.path}`);

export const fetchView = (ref: ViewRef): Promise<ViewDoc> =>
  getJson<ViewDoc>(`${API_ROOT}/${ref.path}`);

export const fetchEntityIndex = (path: string): Promise<EntityIndex> =>
  getJson<EntityIndex>(`${API_ROOT}/${path}`);

export const fetchEntityDocument = (path: string): Promise<EntityDocument> =>
  getJson<EntityDocument>(`${API_ROOT}/${path}`);

/** Raw text of a file shipped inside the API tree (e.g. a chart's CSV). */
export const fetchApiText = (path: string): Promise<string> =>
  fetch(`${API_ROOT}/${path}`).then((response) => {
    if (!response.ok) {
      throw new Error(`${path}: HTTP ${response.status}`);
    }
    return response.text();
  });
