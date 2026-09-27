import type { ChartSpec, Manifest, SectionDoc, TimeseriesDocument } from '../src/api';
import { CONTRIB_DOC, GOV_DOC, MANIFEST, ROUTES } from '../src/test/fixtures.ts';

/** A decodable one-pixel PNG: chart files on disk and the stubbed avatar hosts. */
export const PIXEL_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGP4DwQACfsD/fteaysAAAAASUVORK5CYII=',
  'base64',
);

// Exercise real virtualisation, wrapping, and deliberate truncation without
// a second hand-maintained API schema. All shapes derive from the unit data.
export const PRINT_GOV_DOC: SectionDoc = {
  ...GOV_DOC,
  columns: [...GOV_DOC.columns, { key: 'organisation', label: 'Organisation mix' }],
  rows: Array.from({ length: 125 }, (_, index) => ({
    user: `member-${String(index + 1).padStart(3, '0')}`,
    count: index + 1,
    last_seen: '2026-07-20T00:00:00',
    organisation: 'Hashgraph 45%; LimeChain 25%; Example organisation with a long name 30%',
  })),
  row_count: 125,
};

export const PRINT_CONTRIB_DOC: SectionDoc = {
  ...CONTRIB_DOC,
  rows: Array.from({ length: 620 }, (_, index) => ({
    contributor: `contributor-${String(index + 1).padStart(4, '0')}`,
  })),
  row_count: 620,
};

/** A valid role-stacked timeseries (see src/chartData.ts), one row per bucket. */
export function pipelineDocument(
  id: string,
  frequency: 'year' | 'month',
  buckets: string[],
): TimeseriesDocument {
  return {
    schema_version: 1,
    id,
    org: 'hiero-ledger',
    kind: 'timeseries',
    source: 'roles.csv',
    metric: 'active_contributors_by_role',
    unit: 'Unique active contributors',
    population: 'Each person is counted once per bucket, at their most senior role.',
    dimensions: ['period', 'series'],
    note: 'Read the bars left to right.',
    methodology: ['Resolve roles per bucket.', 'Count each person once.'],
    generated_at: '2026-07-25T10:00:00+00:00',
    mark: 'bar',
    stacked: true,
    normalize: false,
    orientation: 'vertical',
    value_format: 'integer',
    rank: false,
    top_n: null,
    reference: null,
    category: { key: 'bucket', label: 'Period (UTC)' },
    series: [
      { key: 'general_user', label: 'General contributors', color: 'var(--chart-general)' },
      { key: 'triage', label: 'Triage', color: 'var(--chart-triage)' },
      { key: 'committer', label: 'Committers', color: 'var(--chart-committer)' },
      { key: 'maintainer', label: 'Maintainers', color: 'var(--chart-maintainer)' },
    ],
    details: [],
    frequency,
    timezone: 'UTC',
    comparison: null,
    group: null,
    window: { kind: 'calendar', first: buckets[0], last: buckets[buckets.length - 1] },
    rows: buckets.map((bucket, index) => ({
      bucket,
      general_user: 40 + index,
      triage: 3 + (index % 4),
      committer: 10 + (index % 5),
      maintainer: 12 + (index % 3),
      partial: index === buckets.length - 1,
    })),
  };
}

const months = (count: number) =>
  Array.from({ length: count }, (_, index) => {
    const month = 2026 * 12 + 6 - (count - 1) + index;
    return `${Math.floor(month / 12)}-${String((month % 12) + 1).padStart(2, '0')}`;
  });

/** Chart documents by API path; each pipeline variant draws from one of them. */
export const PIPELINE_DOCS = {
  'hiero-ledger/charts/pipeline_yearly.json': pipelineDocument('pipeline_yearly', 'year', [
    '2021',
    '2022',
    '2023',
    '2024',
    '2025',
    '2026',
  ]),
  'hiero-ledger/charts/pipeline_monthly.json': pipelineDocument(
    'pipeline_monthly',
    'month',
    months(24),
  ),
  'hiero-ledger/charts/pipeline_next.json': pipelineDocument('pipeline_next', 'month', months(12)),
} satisfies Record<string, TimeseriesDocument>;

const interactive = (path: keyof typeof PIPELINE_DOCS) => ({ kind: 'timeseries' as const, path });

const pipeline = MANIFEST.orgs['hiero-ledger'].chart_sections.find(
  (section) => section.id === 'pipeline',
)!;
const [yearly, monthly] = pipeline.charts[0].variants;

/** The first slide switches By year / By month; the second, off-screen slide has its own data. */
const PIPELINE_CHARTS: ChartSpec[] = [
  {
    ...pipeline.charts[0],
    variants: [
      { ...yearly, interactive: interactive('hiero-ledger/charts/pipeline_yearly.json') },
      { ...monthly, interactive: interactive('hiero-ledger/charts/pipeline_monthly.json') },
    ],
  },
  {
    ...pipeline.charts[0],
    title: 'The next pipeline chart',
    wide: true,
    variants: [{ ...monthly, interactive: interactive('hiero-ledger/charts/pipeline_next.json') }],
  },
];

export const PRINT_MANIFEST: Manifest = {
  ...MANIFEST,
  orgs: {
    ...MANIFEST.orgs,
    'hiero-ledger': {
      ...MANIFEST.orgs['hiero-ledger'],
      sections: MANIFEST.orgs['hiero-ledger'].sections.map((section) => ({
        ...section,
        row_count:
          section.id === PRINT_GOV_DOC.id
            ? PRINT_GOV_DOC.row_count
            : section.id === PRINT_CONTRIB_DOC.id
              ? PRINT_CONTRIB_DOC.row_count
              : section.row_count,
      })),
      chart_sections: MANIFEST.orgs['hiero-ledger'].chart_sections.map((section) =>
        section.id === 'pipeline'
          ? { ...section, slideshow: true, charts: PIPELINE_CHARTS }
          : section,
      ),
    },
  },
};

export const PRINT_ROUTES: Record<string, unknown> = {
  ...ROUTES,
  ...PIPELINE_DOCS,
  'manifest.json': PRINT_MANIFEST,
  'hiero-ledger/roles.json': PRINT_GOV_DOC,
  'hiero-ledger/profiles.json': PRINT_CONTRIB_DOC,
};
