import type { Manifest, SectionDoc } from '../src/api';
import { CONTRIB_DOC, GOV_DOC, MANIFEST, ROUTES } from '../src/test/fixtures.ts';

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
          ? {
              ...section,
              slideshow: true,
              charts: [
                ...section.charts,
                {
                  ...section.charts[0],
                  title: 'The next pipeline chart',
                  wide: true,
                  variants: [section.charts[0].variants[1]],
                },
              ],
            }
          : section,
      ),
    },
  },
};

export const PRINT_ROUTES: Record<string, unknown> = {
  ...ROUTES,
  'manifest.json': PRINT_MANIFEST,
  'hiero-ledger/roles.json': PRINT_GOV_DOC,
  'hiero-ledger/profiles.json': PRINT_CONTRIB_DOC,
};
