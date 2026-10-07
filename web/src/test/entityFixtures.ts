/**
 * The fixture API's repository and contributor detail views: a manifest that
 * lists entity indexes, the indexes, and one detail document of each kind,
 * shaped exactly as export/entity_views.py publishes them. Plain data, so the
 * component and browser suites can share it.
 */

import type {
  ContributorDocument,
  EntityIndex,
  EntityWindow,
  Manifest,
  RepositoryDocument,
  TimeseriesDocument,
} from '../api';
import { MANIFEST, ROUTES } from './fixtures';

const ORG = 'hiero-ledger';

const WINDOW: EntityWindow = {
  end: '2026-07-25T10:00:00+00:00',
  data_through: '2026-07-24T18:00:00+00:00',
  periods: [
    { key: '7d', label: 'Week', days: 7, start: '2026-07-18T10:00:00+00:00' },
    { key: '30d', label: '1 month', days: 30, start: '2026-06-25T10:00:00+00:00' },
    { key: '365d', label: '1 year', days: 365, start: '2025-07-25T10:00:00+00:00' },
    { key: 'all', label: 'All time', days: null },
  ],
};

const COMMON = {
  schema_version: 1 as const,
  org: ORG,
  generated_at: '2026-07-25T10:00:00+00:00',
  stale: false,
  scope:
    'Tracked activity covers pull requests opened, reviews submitted, pull requests merged, issues opened and labels applied. It does not measure commits, comments, reactions or anything else, and it is not a measure of individual performance.',
  methodology: ['Count one action per event.', 'Count each window from the events inside it.'],
  limits: ['At most 100 reviews per pull request are read.'],
  window: WINDOW,
};

const zero = {
  prs_opened: 0,
  reviews_given: 0,
  merges_done: 0,
  issues_opened: 0,
  labels_applied: 0,
  total_actions: 0,
};
const mixOf = (building: number, reviewing: number, organizing: number) => {
  const total = building + reviewing + organizing;
  const share = (count: number) => (total ? Math.round((count / total) * 100) : 0);
  return {
    building_and_fixing: { count: building, share: share(building) },
    reviewing_and_guiding: { count: reviewing, share: share(reviewing) },
    organizing_and_answering: { count: organizing, share: share(organizing) },
  };
};

const TREND: TimeseriesDocument = {
  schema_version: 1,
  id: 'repository-trend',
  org: ORG,
  kind: 'timeseries',
  source: 'entity_repo_monthly.csv',
  metric: 'tracked_actions',
  unit: 'Tracked actions',
  population: 'Every tracked action in this repository by a person.',
  dimensions: ['period', 'series'],
  mark: 'bar',
  stacked: true,
  normalize: false,
  orientation: 'vertical',
  value_format: 'integer',
  rank: false,
  top_n: null,
  reference: null,
  value_max: null,
  frequency: 'month',
  timezone: 'UTC',
  comparison: null,
  group: null,
  category: { key: 'bucket', label: 'Month (UTC)' },
  window: { kind: 'calendar', first: '2026-06', last: '2026-07' },
  series: [
    { key: 'prs_opened', label: 'PRs opened', color: 'var(--chart-1)' },
    { key: 'reviews_given', label: 'Reviews', color: 'var(--chart-2)' },
  ],
  details: [],
  rows: [
    { bucket: '2026-06', prs_opened: 3, reviews_given: 1, partial: false },
    { bucket: '2026-07', prs_opened: 2, reviews_given: 4, partial: true },
  ],
};

export const REPO_DOC: RepositoryDocument = {
  ...COMMON,
  kind: 'repository',
  id: 'hiero-sdk-js',
  name: 'hiero-sdk-js',
  full_name: `${ORG}/hiero-sdk-js`,
  github_url: `https://github.com/${ORG}/hiero-sdk-js`,
  population: 'Every tracked action in this repository by a person.',
  source: ['entity_repo_activity.csv', 'entity_repo_contributor_activity.csv'],
  first_active: '2024-02-01 09:00:00+00:00',
  last_active: '2026-07-24 12:00:00+00:00',
  summary: {
    all: {
      ...zero,
      prs_opened: 40,
      reviews_given: 12,
      merges_done: 9,
      total_actions: 61,
      active_contributors: 4,
    },
    '365d': {
      ...zero,
      prs_opened: 11,
      reviews_given: 5,
      total_actions: 16,
      active_contributors: 3,
    },
    '30d': { ...zero, prs_opened: 3, total_actions: 3, active_contributors: 2 },
    // A quiet week is published as zeros.
    '7d': { ...zero, active_contributors: 0 },
  },
  mix: {
    all: mixOf(40, 21, 0),
    '365d': mixOf(11, 5, 0),
    '30d': mixOf(3, 0, 0),
    '7d': mixOf(0, 0, 0),
  },
  trend: TREND,
  contributors: {
    id: 'repository-contributors',
    title: 'Active contributors',
    description: 'Everyone with a tracked action in this repository in the window.',
    source: 'entity_repo_contributor_activity.csv',
    columns: [
      { key: 'contributor', label: 'Contributor' },
      { key: 'prs_opened', label: 'PRs opened', format: 'number' },
      { key: 'total_actions', label: 'All tracked actions', format: 'number' },
    ],
    rows: [
      { contributor: 'alice', prs_opened: 30, total_actions: 41 },
      { contributor: 'bob', prs_opened: 10, total_actions: 20 },
    ],
    row_count: 2,
    periods: {
      '7d': [],
      '30d': [{ contributor: 'alice', prs_opened: 3, total_actions: 3 }],
      '365d': [],
    },
    generated_at: '2026-07-25T10:00:00+00:00',
  },
  related: [
    {
      id: 'releases',
      title: 'Releases',
      source: ['release_repo_summary.csv', 'release_timeline.csv'],
      fields: [
        {
          key: 'days_since_last_release',
          label: 'Days since last release',
          value: 12,
          format: 'number',
        },
      ],
      list: {
        title: 'Recent releases',
        source: 'release_timeline.csv',
        columns: [{ key: 'tag_name', label: 'Tag' }],
        rows: [{ tag_name: 'v2.1.0' }],
      },
    },
    {
      id: 'hips',
      title: 'HIP engagement',
      source: ['hip_repo_engagement.csv'],
      links: [{ macro: 'Governance', id: 'roles', title: 'Role holders' }],
      fields: [
        {
          key: 'distinct_hips_merged',
          label: 'Distinct HIPs with merged PRs',
          value: 7,
          format: 'number',
        },
      ],
    },
    {
      id: 'onboarding',
      title: 'Onboarding',
      source: ['difficulty_by_repo.csv'],
      fields: [],
      links: [],
    },
  ],
  unavailable: ['Security'],
};

export const PERSON_DOC: ContributorDocument = {
  ...COMMON,
  kind: 'contributor',
  id: 'alice',
  login: 'alice',
  github_url: 'https://github.com/alice',
  population: 'Every tracked action by this person across the organisation.',
  source: ['entity_contributor_activity.csv'],
  first_active: '2024-03-01 09:00:00+00:00',
  last_active: '2026-07-24 12:00:00+00:00',
  summary: {
    all: { ...zero, prs_opened: 30, issues_opened: 11, total_actions: 41, repos_touched: 2 },
    '365d': { ...zero, prs_opened: 8, total_actions: 8, repos_touched: 1 },
    '30d': { ...zero, prs_opened: 3, total_actions: 3, repos_touched: 1 },
    '7d': { ...zero, repos_touched: 0 },
  },
  mix: {
    all: mixOf(30, 0, 11),
    '365d': mixOf(8, 0, 0),
    '30d': mixOf(3, 0, 0),
    '7d': mixOf(0, 0, 0),
  },
  trend: null,
  repositories: {
    id: 'contributor-repositories',
    title: 'Repositories',
    description: 'Each repository with a tracked action by this person in the window.',
    source: 'entity_repo_contributor_activity.csv',
    columns: [
      { key: 'repo', label: 'Repository' },
      { key: 'total_actions', label: 'All tracked actions', format: 'number' },
      { key: 'last_active', label: 'Last active (UTC)', format: 'date' },
    ],
    rows: [
      { repo: `${ORG}/hiero-sdk-js`, total_actions: 41, last_active: '2026-07-24 12:00:00+00:00' },
      { repo: `${ORG}/hiero-docs`, total_actions: 0, last_active: '2025-01-02 12:00:00+00:00' },
    ],
    row_count: 2,
    periods: { '7d': [], '30d': [], '365d': [] },
  },
};

const index = (kind: 'repositories' | 'contributors', rows: EntityIndex['rows']): EntityIndex => ({
  schema_version: 1,
  kind: `${kind}-index`,
  org: ORG,
  generated_at: '2026-07-25T10:00:00+00:00',
  detail_path: `${ORG}/entities/${kind}/{id}.json`,
  window: WINDOW,
  rows,
});

export const REPOSITORY_INDEX = index('repositories', [
  {
    id: 'hiero-sdk-js',
    name: 'hiero-sdk-js',
    full_name: `${ORG}/hiero-sdk-js`,
    total_actions: 61,
    last_active: null,
  },
]);
export const CONTRIBUTOR_INDEX = index('contributors', [
  { id: 'alice', login: 'alice', total_actions: 41, last_active: null },
  { id: 'bob', login: 'bob', total_actions: 20, last_active: null },
]);

export const ENTITY_MANIFEST: Manifest = {
  ...MANIFEST,
  // Every period the real manifest labels, as the detail views' tables offer all three.
  period_labels: { '7d': 'Week', '30d': '1 month', '365d': '1 year' },
  orgs: {
    ...MANIFEST.orgs,
    [ORG]: {
      ...MANIFEST.orgs[ORG],
      entities: {
        repositories: { path: `${ORG}/entities/repositories.json`, count: 1 },
        contributors: { path: `${ORG}/entities/contributors.json`, count: 2 },
      },
    },
  },
};

/** Every fixture route, with the manifest listing entities and their documents added. */
export const ENTITY_ROUTES: Record<string, unknown> = {
  ...ROUTES,
  'manifest.json': ENTITY_MANIFEST,
  [`${ORG}/entities/repositories.json`]: REPOSITORY_INDEX,
  [`${ORG}/entities/contributors.json`]: CONTRIBUTOR_INDEX,
  [`${ORG}/entities/repositories/hiero-sdk-js.json`]: REPO_DOC,
  [`${ORG}/entities/contributors/alice.json`]: PERSON_DOC,
};
