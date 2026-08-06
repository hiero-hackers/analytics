/**
 * Typed client for the analytics data API (outputs/data/api/v1).
 *
 * The shapes here mirror what `export/data_api.py` emits and are the only
 * coupling between this app and the Python side: the app renders whatever the
 * manifest lists, so new sections and orgs appear without frontend changes.
 */

export interface ColumnSpec {
  key: string;
  label: string;
  /**
   * Optional display format, rendered by `components/FormattedCell`:
   * hip | date | link | evidence | status | flag | presence | number.
   * The valid set is declared once in Python (`dashboard_spec.COLUMN_FORMATS`)
   * and enforced there, so a spec typo fails a test rather than shipping as an
   * unformatted column.
   */
  format?: string;
}

export interface SectionRef {
  id: string;
  macro: string;
  title: string;
  row_count: number;
  path: string;
}

export interface ChartVariant {
  label: string;
  file: string;
  /** Intrinsic pixel size, when the emitter could read it — lets the browser
   *  reserve the image's box so loading charts don't shift the page. */
  width?: number;
  height?: number;
}

export interface ChartSpec {
  title: string;
  variants: ChartVariant[];
  note?: string;
  methodology?: string[];
  wide?: boolean;
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
  slideshow?: boolean;
  charts: ChartSpec[];
  /** A companion CSV copied into the API tree, offered as a download. */
  download?: ChartDownload;
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
  kind: "complete" | "none" | "partial";
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
  kind: "matrix";
  macro: string;
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
  kind: "board";
  macro: string;
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
  /** Display labels for rolling periods ("30d" -> "30 days"). */
  period_labels?: Record<string, string>;
  provenance: { git_sha: string | null; data_as_of: string | null };
  orgs: Record<string, OrgEntry>;
}

export type Row = Record<string, unknown>;

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

export const fetchManifest = (): Promise<Manifest> => getJson<Manifest>(`${API_ROOT}/manifest.json`);

export const fetchSection = (ref: SectionRef): Promise<SectionDoc> =>
  getJson<SectionDoc>(`${API_ROOT}/${ref.path}`);

export const fetchView = (ref: ViewRef): Promise<ViewDoc> => getJson<ViewDoc>(`${API_ROOT}/${ref.path}`);

/** Raw text of a file shipped inside the API tree (e.g. a chart's CSV). */
export const fetchApiText = (path: string): Promise<string> =>
  fetch(`${API_ROOT}/${path}`).then((response) => {
    if (!response.ok) {
      throw new Error(`${path}: HTTP ${response.status}`);
    }
    return response.text();
  });
