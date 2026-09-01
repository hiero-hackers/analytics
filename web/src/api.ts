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
  'hip' | 'date' | 'link' | 'evidence' | 'status' | 'flag' | 'presence' | 'number';

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

export interface ChartVariant {
  label: string;
  file: string;
  /** Intrinsic pixel size, when the emitter could read it — lets the browser
   *  reserve the image's box so loading charts don't shift the page. */
  width?: number;
  height?: number;
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
  /** If set and the matching view (by id, in ViewDoc) loaded successfully,
   *  this slide renders that live instead of its PNG variants — the variants
   *  stay in place underneath as the fallback, not removed by this. */
  live_view_id?: string;
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

/** A contributor-by-month activity grid, rendered client-side instead of a PNG. */
export interface HeatmapView {
  id: string;
  kind: "heatmap";
  macro: string;
  /** The named section group this view renders under. */
  group?: string;
  title: string;
  description: string;
  badge: string;
  source: string;
  /** Row labels, e.g. contributor logins, busiest first. */
  rows: string[];
  /** Column labels, e.g. "2026-01". */
  columns: string[];
  /** [row][column] cell values. Same order as rows/columns. */
  values: number[][];
  /** Highest value in this dataset — cells interpolate colour against this,
   *  not a fixed bucket count, since activity scores are unbounded. */
  max_value: number;
  /** Path to the PNG this view supersedes, used if the view fails to load. */
  /** The PNG this view supersedes, or absent if one was never produced —
   *  never a path guaranteed to 404. */
  png_fallback?: string | null;
  generated_at?: string;
  stale?: boolean;
}

export type ViewDoc = MatrixView | BoardView | HeatmapView;

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

/** Deploy-relative roots: the app, the API, and the chart PNGs ship together. */
const BASE = import.meta.env.BASE_URL;
export const API_ROOT = `${BASE}data/api/v1`;
export const chartUrl = (file: string): string => `${BASE}${file}`;

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

/** Raw text of a file shipped inside the API tree (e.g. a chart's CSV). */
export const fetchApiText = (path: string): Promise<string> =>
  fetch(`${API_ROOT}/${path}`).then((response) => {
    if (!response.ok) {
      throw new Error(`${path}: HTTP ${response.status}`);
    }
    return response.text();
  });
