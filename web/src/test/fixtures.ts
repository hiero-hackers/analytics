/**
 * A miniature but structurally complete data API: two orgs, one macro with
 * charts + tables + metrics (only for the primary org) and one macro both
 * orgs share, so org-tab behaviour is exercised. `stubApi` serves it through
 * a fetch stub keyed by URL suffix — the same contract the real API honours.
 */

import { vi } from 'vitest';
import type { BoardView, Manifest, MatrixView, SectionDoc } from '../api';

export const GOV_DOC: SectionDoc = {
  id: 'roles',
  title: 'Role holders',
  description: 'Who holds each governance role.',
  group: 'Roles & teams',
  macro: 'Governance',
  source: 'roles.csv',
  columns: [
    { key: 'user', label: 'user' },
    { key: 'count', label: 'count', format: 'number' },
    { key: 'last_seen', label: 'last seen', format: 'date' },
  ],
  rows: [
    { user: 'carol', count: 3, last_seen: '2026-07-01T00:00:00' },
    { user: 'alice', count: 2490, last_seen: '2026-07-20T00:00:00' },
    { user: 'bob', count: 7, last_seen: '2026-07-10T00:00:00' },
  ],
  row_count: 3,
  action: { url: 'https://example.test/correct', label: 'Suggest a correction' },
  generated_at: '2026-07-25T10:00:00+00:00',
  periods: { '30d': [{ user: 'alice', count: 4, last_seen: '2026-07-20T00:00:00' }] },
};

export const CONTRIB_DOC: SectionDoc = {
  id: 'profiles',
  title: 'Contributor profiles',
  description: 'Per-contributor activity.',
  group: 'All contributors',
  macro: 'Contributors',
  source: 'profiles.csv',
  columns: [{ key: 'contributor', label: 'contributor' }],
  rows: [{ contributor: 'alice' }, { contributor: 'bob' }],
  row_count: 2,
};

export const HACKERS_DOC: SectionDoc = {
  ...CONTRIB_DOC,
  rows: [{ contributor: 'erin' }],
  row_count: 1,
};

/**
 * A role-tabbed table: the two tabs are disjoint populations with genuinely
 * different shapes (the first column is labelled for the role it names), which
 * is what the Organisation-diversity tables look like once merged.
 */
export const AFFILIATIONS_DOC: SectionDoc = {
  id: 'affiliations',
  title: 'Organisation affiliations — reference',
  description: 'Each maintainer and the organisation they were mapped to.',
  group: 'Organisation diversity',
  macro: 'Diversity',
  source: 'maintainer_affiliations.csv',
  columns: [
    { key: 'login', label: 'maintainer' },
    { key: 'organisation', label: 'organisation' },
  ],
  rows: [
    { login: 'alice', organisation: 'Hashgraph' },
    { login: 'bob', organisation: 'LimeChain' },
  ],
  row_count: 2,
  action: { url: 'https://example.test/affiliation', label: 'Suggest an affiliation fix' },
  generated_at: '2026-07-25T10:00:00+00:00',
  variants: [
    {
      id: 'affiliations',
      label: 'Maintainers',
      title: 'Maintainer affiliations — reference',
      description: 'Each maintainer and the organisation they were mapped to.',
      source: 'maintainer_affiliations.csv',
      columns: [
        { key: 'login', label: 'maintainer' },
        { key: 'organisation', label: 'organisation' },
      ],
      rows: [
        { login: 'alice', organisation: 'Hashgraph' },
        { login: 'bob', organisation: 'LimeChain' },
      ],
      row_count: 2,
      action: { url: 'https://example.test/affiliation', label: 'Suggest an affiliation fix' },
      generated_at: '2026-07-25T10:00:00+00:00',
    },
    {
      id: 'committeraffiliations',
      label: 'Committers',
      title: 'Committer affiliations — reference',
      description: 'Each committer, whose highest role anywhere is committer.',
      source: 'committer_affiliations.csv',
      columns: [
        { key: 'login', label: 'committer' },
        { key: 'organisation', label: 'organisation' },
      ],
      rows: [{ login: 'dave', organisation: 'BlockyDevs' }],
      row_count: 1,
      action: { url: 'https://example.test/affiliation', label: 'Suggest an affiliation fix' },
      generated_at: '2026-07-26T10:00:00+00:00',
    },
  ],
};

export const HIP_EVIDENCE_DOC: SectionDoc = {
  id: 'hip-evidence',
  title: 'Evidence (per PR)',
  description: 'The audit trail.',
  group: 'Evidence',
  macro: 'HIPs',
  source: 'hip_pr_evidence.csv',
  columns: [
    { key: 'hip', label: 'HIP', format: 'hip' },
    { key: 'repo', label: 'repository' },
    { key: 'pr_number', label: 'PR' },
  ],
  rows: [
    {
      hip: 1200,
      repo: 'hiero-ledger/consensus',
      pr_number: 88,
      pr_title: 'feat: HIP-1200 throughput',
      pr_state: 'MERGED',
      pr_merged_at: '2026-06-02T00:00:00.000',
      match_sources: 'title|branch',
      qualifier: null,
      counted: true,
      snippet: '…HIP-1200 throughput…',
    },
    {
      hip: 1200,
      repo: 'hiero-ledger/consensus',
      pr_number: 91,
      pr_title: 'chore: prepare for HIP-1200',
      pr_state: 'OPEN',
      pr_merged_at: null,
      match_sources: 'body',
      qualifier: 'prepares for',
      counted: false,
      snippet: '…prepare for HIP-1200…',
    },
  ],
  row_count: 2,
};

/**
 * One column per `ColumnFormat` value, so every format the union allows is
 * exercised by at least one fixture column — this is what keeps the TS union
 * honest against `FormattedCell`'s switch as both evolve.
 */
export const ALL_FORMATS_DOC: SectionDoc = {
  id: 'all-formats',
  title: 'All formats',
  description: 'One column per supported display format.',
  group: 'Formats',
  macro: 'Governance',
  source: 'all_formats.csv',
  columns: [
    { key: 'hip', label: 'hip', format: 'hip' },
    { key: 'date', label: 'date', format: 'date' },
    { key: 'link', label: 'link', format: 'link' },
    { key: 'evidence', label: 'evidence', format: 'evidence' },
    { key: 'status', label: 'status', format: 'status' },
    { key: 'flag', label: 'flag', format: 'flag' },
    { key: 'presence', label: 'presence', format: 'presence' },
    { key: 'number', label: 'number', format: 'number' },
    { key: 'staleness', label: 'staleness', format: 'staleness' },
  ],
  rows: [
    {
      hip: 1200,
      date: '2026-07-20T00:00:00',
      link: 'https://example.test/pr/1',
      evidence: 'merged',
      status: 'Final',
      flag: 'true',
      presence: 'true',
      number: 2490,
      staleness: 'overdue',
    },
  ],
  row_count: 1,
};

export const MATRIX_DOC: MatrixView = {
  id: 'hip-matrix',
  kind: 'matrix',
  macro: 'HIPs',
  title: 'Implementation coverage matrix',
  description: 'Merged PRs referencing each HIP, per component.',
  badge: '3 HIPs',
  source: 'hip_repo_activity.csv',
  row_header: 'Governance',
  note_header: 'No SDK PRs found in',
  bands: [
    { label: 'Services', span: 1 },
    { label: 'SDKs', span: 2 },
  ],
  columns: [
    { key: 'hiero-ledger/consensus', label: 'consensus', band: 'Services' },
    { key: 'hiero-ledger/sdk-java', label: 'java', band: 'SDKs' },
    { key: 'hiero-ledger/sdk-go', label: 'go', band: 'SDKs' },
  ],
  rows: [
    {
      key: 1200,
      label: 'HIP-1200',
      sublabel: 'Throughput',
      status: 'Approved',
      cells: [
        { key: 'hiero-ledger/consensus', merged: 3, open: 1 },
        { key: 'hiero-ledger/sdk-java', merged: 0, open: 2 },
        { key: 'hiero-ledger/sdk-go', merged: 0, open: 0 },
      ],
      note: { kind: 'partial', text: 'java · go', items: ['java', 'go'] },
    },
    {
      key: 1100,
      label: 'HIP-1100',
      sublabel: 'Airdrops',
      status: 'Final',
      cells: [
        { key: 'hiero-ledger/consensus', merged: 1, open: 0 },
        { key: 'hiero-ledger/sdk-java', merged: 1, open: 0 },
        { key: 'hiero-ledger/sdk-go', merged: 44, open: 0 },
      ],
      note: { kind: 'complete', text: '✓ all SDKs' },
    },
    {
      key: 1000,
      label: 'HIP-1000',
      sublabel: 'Dormant',
      status: 'Deferred',
      cells: [
        { key: 'hiero-ledger/consensus', merged: 0, open: 0 },
        { key: 'hiero-ledger/sdk-java', merged: 0, open: 0 },
        { key: 'hiero-ledger/sdk-go', merged: 0, open: 0 },
      ],
      note: { kind: 'none', text: 'no activity found' },
    },
  ],
  ramp: ['#cde2fb', '#9ec5f4', '#5598e7', '#2a78d6', '#104281'],
  ramp_ceilings: [2, 5, 15, 40],
  filters: ['Final', 'Approved', 'Deferred'],
  evidence_section: 'hip-evidence',
  generated_at: '2026-07-25T09:00:00+00:00',
};

export const BOARD_DOC: BoardView = {
  id: 'hip-board',
  kind: 'board',
  macro: 'HIPs',
  title: 'Where specs sit in governance',
  description: 'Every HIP spec, placed by its lifecycle status.',
  badge: '3 specs',
  source: 'hip_summary.csv',
  columns: [
    {
      title: 'Approved (incl. legacy Accepted)',
      items: [{ key: 1200, label: 'HIP-1200', title: 'Throughput', status: 'Approved' }],
    },
    {
      title: 'Final',
      items: [{ key: 1100, label: 'HIP-1100', title: 'Airdrops', status: 'Final' }],
    },
    { title: 'Active', items: [] },
    {
      title: 'Retired',
      items: [{ key: 1000, label: 'HIP-1000', title: 'Dormant', status: 'Deferred' }],
    },
  ],
  target_view: 'hip-matrix',
};

export const MANIFEST: Manifest = {
  version: 'v1',
  generated_at: '2026-07-25T22:00:00+00:00',
  macro_glossaries: {
    Governance: {
      title: 'How to read this — what each column means',
      layout: 'definitions',
      terms: [{ term: 'PRs', definition: 'pull requests opened; *general* = no special role.' }],
      note: 'Comments and reactions are not counted.',
    },
    HIPs: {
      title: 'How to read this tab — what the numbers mean',
      layout: 'notes',
      terms: [
        { term: 'What is measured.', definition: 'Referencing PRs — *evidence*, never proof.' },
      ],
    },
  },
  period_labels: { '30d': '1 month' },
  issues_url: 'https://example.test/issues',
  macro_absent_notes: {
    Governance:
      "Governance analytics need a published governance config; this org doesn't have one.",
  },
  provenance: { git_sha: 'abc1234', data_as_of: '2026-07-25T21:00:00+00:00' },
  orgs: {
    'hiero-ledger': {
      views: [
        {
          id: 'hip-board',
          macro: 'HIPs',
          kind: 'board',
          title: 'Where specs sit in governance',
          path: 'hiero-ledger/hip-board.json',
        },
        {
          id: 'hip-matrix',
          macro: 'HIPs',
          kind: 'matrix',
          title: 'Implementation coverage matrix',
          path: 'hiero-ledger/hip-matrix.json',
        },
      ],
      sections: [
        {
          id: 'roles',
          macro: 'Governance',
          title: 'Role holders',
          row_count: 3,
          path: 'hiero-ledger/roles.json',
        },
        {
          id: 'hip-evidence',
          macro: 'HIPs',
          title: 'Evidence (per PR)',
          row_count: 2,
          path: 'hiero-ledger/hip-evidence.json',
        },
        {
          id: 'profiles',
          macro: 'Contributors',
          title: 'Contributor profiles',
          row_count: 2,
          path: 'hiero-ledger/profiles.json',
        },
        {
          id: 'affiliations',
          macro: 'Diversity',
          title: 'Organisation affiliations — reference',
          row_count: 2,
          path: 'hiero-ledger/affiliations.json',
        },
        // Absorbed: still listed and still fetchable (v1 may not withdraw an
        // id), but its rows travel inside the card above as a role tab.
        {
          id: 'committeraffiliations',
          macro: 'Diversity',
          title: 'Committer affiliations — reference',
          row_count: 1,
          path: 'hiero-ledger/committeraffiliations.json',
          absorbed_by: 'affiliations',
        },
      ],
      chart_sections: [
        {
          id: 'pipeline',
          macro: 'Governance',
          title: 'Maintainer pipeline',
          group: 'Pipeline charts',
          description: 'How the pipeline moved.',
          charts: [
            {
              title: 'Unique active contributors by role',
              variants: [
                { label: 'By year', file: 'charts/org/hiero-ledger/pipeline_yearly.png' },
                { label: 'By month', file: 'charts/org/hiero-ledger/pipeline_monthly.png' },
              ],
              note: 'How to read this chart.',
              methodology: ['Step one.', 'Step two.'],
            },
          ],
        },
        // Three charts on one card: two share a Maintainers/Committers axis
        // (so the card owns it), the third has none of its own.
        {
          id: 'org-diversity',
          macro: 'Diversity',
          title: 'Organisation diversity',
          group: 'Organisation diversity',
          description: 'Where write authority sits.',
          downloads: {
            Maintainers: {
              name: 'maintainer_affiliations.csv',
              path: 'hiero-ledger/maintainer_affiliations.csv',
            },
            Committers: {
              name: 'committer_affiliations.csv',
              path: 'hiero-ledger/committer_affiliations.csv',
            },
          },
          charts: [
            {
              title: 'Role-holders by organisation',
              variants: [
                {
                  label: 'Maintainers',
                  file: 'charts/org/hiero-ledger/affiliation_donut.png',
                  note: 'The maintainer bench by employer.',
                  methodology: ['Count maintainers.'],
                },
                {
                  label: 'Committers',
                  file: 'charts/org/hiero-ledger/affiliation_donut_committers.png',
                  note: 'The committer bench by employer.',
                  methodology: ['Count committers.'],
                },
              ],
              note: 'The maintainer bench by employer.',
              methodology: ['Count maintainers.'],
            },
            {
              title: 'Single-employer repos by org',
              variants: [
                {
                  label: 'Maintainers',
                  file: 'charts/org/hiero-ledger/single_employer_repos_by_org.png',
                },
                {
                  label: 'Committers',
                  file: 'charts/org/hiero-ledger/single_employer_repos_by_org_committers.png',
                },
              ],
            },
            {
              title: 'Single-employer teams by org',
              variants: [
                {
                  label: 'Single-employer teams by org',
                  file: 'charts/org/hiero-ledger/single_employer_teams_by_org.png',
                },
              ],
              note: 'Teams are membership-based, so they have no role tabs.',
            },
          ],
        },
      ],
      metrics: {
        Governance: [
          {
            label: 'maintainers',
            value: 103,
            note: 'People whose highest role anywhere is maintainer.',
            methodology: [
              'Resolve roles per repository.',
              'Reduce to the most senior role.',
              'Count them.',
            ],
          },
          { label: 'quiet teams', value: 2 },
        ],
      },
    },
    'hiero-hackers': {
      sections: [
        {
          id: 'profiles',
          macro: 'Contributors',
          title: 'Contributor profiles',
          row_count: 1,
          path: 'hiero-hackers/profiles.json',
        },
      ],
      chart_sections: [],
      metrics: {},
    },
  },
};

const ROUTES: Record<string, unknown> = {
  'manifest.json': MANIFEST,
  'hiero-ledger/roles.json': GOV_DOC,
  'hiero-ledger/hip-evidence.json': HIP_EVIDENCE_DOC,
  'hiero-ledger/hip-board.json': BOARD_DOC,
  'hiero-ledger/hip-matrix.json': MATRIX_DOC,
  'hiero-ledger/profiles.json': CONTRIB_DOC,
  'hiero-ledger/affiliations.json': AFFILIATIONS_DOC,
  'hiero-ledger/committeraffiliations.json': AFFILIATIONS_DOC.variants?.[1],
  'hiero-hackers/profiles.json': HACKERS_DOC,
  // Chart companion CSVs travel inside the API tree as raw text.
  'hiero-ledger/maintainer_affiliations.csv': 'login,organisation\nalice,Hashgraph\n',
  'hiero-ledger/committer_affiliations.csv': 'login,organisation\ndave,BlockyDevs\n',
};

/**
 * Stub global fetch to serve the fixture API; returns the spy for assertions.
 * `overrides` lets a test intercept specific routes (e.g. to delay or fail a
 * request) while every other route still serves its normal fixture — so a
 * test controlling one request doesn't have to also know every other request
 * the page happens to make.
 */
export function stubApi(overrides: Record<string, () => Response | Promise<Response>> = {}) {
  return vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const key = String(url);
      const override = Object.entries(overrides).find(([suffix]) => key.endsWith(suffix));
      if (override) return override[1]();
      const match = Object.entries(ROUTES).find(([suffix]) => key.endsWith(suffix));
      if (!match) {
        return new Response('not found', { status: 404 });
      }
      // CSV companions are served verbatim; everything else is a JSON document.
      const body = typeof match[1] === 'string' ? match[1] : JSON.stringify(match[1]);
      return new Response(body, { status: 200 });
    }),
  );
}
