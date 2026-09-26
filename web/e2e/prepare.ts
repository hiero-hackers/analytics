/** Stage the built app beside the same typed API fixtures used by Vitest. */
import { cp, mkdir, rm, writeFile, access } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { PRINT_MANIFEST, PRINT_ROUTES } from './fixtures.ts';

const site = resolve('.e2e/site');
await rm(site, { recursive: true, force: true });
await cp('dist', site, { recursive: true });

async function write(relativePath: string, data: string | Uint8Array) {
  const target = resolve(site, relativePath);
  if (!target.startsWith(`${site}/`)) throw new Error(`Fixture path escapes site: ${relativePath}`);
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, data);
}

for (const [path, value] of Object.entries(PRINT_ROUTES)) {
  await write(`data/api/v1/${path}`, typeof value === 'string' ? value : JSON.stringify(value));
}

// Images only need a real decoded pixel for loading/lightbox smoke checks.
// Layout and printed chart readability are also checked against real PNGs
// during the manual PDF review; no network is needed by this suite.
const png = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGP4DwQACfsD/fteaysAAAAASUVORK5CYII=',
  'base64',
);
for (const entry of Object.values(PRINT_MANIFEST.orgs)) {
  for (const section of entry.chart_sections) {
    for (const chart of section.charts) {
      for (const variant of chart.variants) await write(variant.file, png);
    }
  }
  // Every reference must resolve on disk. A new manifest entry without data
  // should fail setup loudly instead of silently shrinking what gets tested.
  for (const ref of [...entry.sections, ...(entry.views ?? [])]) {
    await access(resolve(site, 'data/api/v1', ref.path));
  }
  for (const section of entry.chart_sections) {
    const downloads = section.download
      ? [section.download]
      : Object.values(section.downloads ?? {});
    for (const download of downloads) await access(resolve(site, 'data/api/v1', download.path));
  }
}
