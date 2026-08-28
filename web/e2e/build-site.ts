/**
 * Stages the static site the smoke suite runs against.
 *
 * The layout is the one CI actually deploys (see `dashboard-preview.yml`): the
 * built app at the root, the data API beneath it at `data/api/v1`, and the
 * chart PNGs at `charts/`. Because the app resolves both from `BASE_URL`,
 * serving this directory needs no proxy and no test-only app config.
 *
 * The API content is the unit suite's fixture, written out as real files, so
 * both suites read one source of truth and `tsc` keeps it honest against the
 * `api.ts` types. Staging into its own directory rather than writing into
 * `dist/` keeps the build output a clean, deployable artifact.
 *
 * Driven by `serve.ts`. The imports below carry explicit `.ts` extensions
 * because nothing transpiles this file; Node strips the types itself.
 */

import { Buffer } from 'node:buffer';
import { existsSync } from 'node:fs';
import { cp, mkdir, rm, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Manifest } from '../src/api.ts';
import { MANIFEST, ROUTES } from '../src/test/fixtures.ts';

const WEB_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const DIST_DIR = join(WEB_ROOT, 'dist');
/** Where the assembled site lands; `.gitignore`d, rebuilt on every run. */
export const SITE_DIR = join(WEB_ROOT, '.e2e-site');
const API_DIR = join(SITE_DIR, 'data', 'api', 'v1');

/**
 * A 1x1 PNG standing in for every chart the manifest lists. They have to exist:
 * a missing image is a failed request that Chromium reports to the console, and
 * the suite's headline assertion is that the console stays clean.
 */
const PLACEHOLDER_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=',
  'base64',
);

/** Stands in for a chart's companion CSV, offered as a download beside it. */
const PLACEHOLDER_CSV = 'label,value\nplaceholder,1\n';

/** Every file the manifest points at, split by where it has to land. */
function referenced(manifest: Manifest) {
  const documents = ['manifest.json'];
  const charts: string[] = [];
  const downloads: string[] = [];
  for (const org of Object.values(manifest.orgs)) {
    for (const section of org.sections ?? []) documents.push(section.path);
    for (const view of org.views ?? []) documents.push(view.path);
    for (const section of org.chart_sections ?? []) {
      if (section.download) downloads.push(section.download.path);
      for (const chart of section.charts) {
        for (const variant of chart.variants) charts.push(variant.file);
      }
    }
  }
  // Deduplicated: two orgs may legitimately point at one document or chart, and
  // neither writing it twice nor naming it twice in a failure helps anyone.
  return {
    documents: [...new Set(documents)],
    charts: [...new Set(charts)],
    downloads: [...new Set(downloads)],
  };
}

async function write(path: string, body: string | Buffer): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, body);
}

export async function buildSite(): Promise<string> {
  if (!existsSync(DIST_DIR)) {
    throw new Error(`no build to stage at ${DIST_DIR} — run \`npm run build\` first.`);
  }

  await rm(SITE_DIR, { recursive: true, force: true });
  await cp(DIST_DIR, SITE_DIR, { recursive: true });

  for (const [route, doc] of Object.entries(ROUTES)) {
    await write(join(API_DIR, route), JSON.stringify(doc));
  }

  const { documents, charts, downloads } = referenced(MANIFEST);
  for (const file of charts) await write(join(SITE_DIR, file), PLACEHOLDER_PNG);
  for (const file of downloads) await write(join(API_DIR, file), PLACEHOLDER_CSV);

  // The manifest is the app's only instruction sheet, so anything it names has
  // to be on disk. Checking the staged tree rather than the fixture object
  // catches both halves: a section added to the manifest without a matching
  // route, and a write that silently landed somewhere else. Without this a
  // gap just renders a smaller dashboard, which every assertion below would
  // happily pass.
  //
  // The two kinds of gap have different causes, so they are reported apart: a
  // document is missing because `ROUTES` lacks it, while a chart or download is
  // missing only if the emitting loops above have fallen out of step with what
  // `referenced()` walks. One remedy pointed at both would send the reader to
  // the wrong file half the time.
  const missingDocuments = documents.filter((file) => !existsSync(join(API_DIR, file)));
  const missingPlaceholders = [
    ...downloads
      .filter((file) => !existsSync(join(API_DIR, file)))
      .map((file) => `data/api/v1/${file}`),
    ...charts.filter((file) => !existsSync(join(SITE_DIR, file))),
  ];
  if (missingDocuments.length > 0 || missingPlaceholders.length > 0) {
    const report = ['the fixture manifest points at files the staged site does not have:'];
    if (missingDocuments.length > 0) {
      report.push(
        '  documents, which are served from ROUTES — add them in src/test/fixtures.ts:',
        ...missingDocuments.map((file) => `    data/api/v1/${file}`),
      );
    }
    if (missingPlaceholders.length > 0) {
      report.push(
        '  placeholders, which this script writes — its emit loops no longer cover everything referenced():',
        ...missingPlaceholders.map((file) => `    ${file}`),
      );
    }
    throw new Error(report.join('\n'));
  }

  return SITE_DIR;
}
