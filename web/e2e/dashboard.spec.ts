/**
 * Boot smoke test for the built dashboard.
 *
 * The vitest suite renders components against fixture objects with `fetch`
 * stubbed, so three things it can never see: whether the built bundle boots at
 * all, whether the app's base-relative URLs resolve against real files, and
 * whether the page honours its own Content-Security-Policy — jsdom does not
 * enforce CSP, so an inline script or an off-origin asset would pass `npm test`
 * and break only in production. All three surface here as console errors.
 *
 * Expectations are derived from the same fixture manifest the site is built
 * from, so extending the fixture extends the coverage rather than breaking it.
 */

import { expect, test, type Page } from '@playwright/test';
import type { Manifest } from '../src/api.ts';
import { MANIFEST } from '../src/test/fixtures.ts';

interface Watch {
  /** Anything the browser reported as broken while the test ran. */
  problems: string[];
  /** Requests aimed off the local server, which this suite refuses to make. */
  external: string[];
}

/**
 * Records browser-reported failures and blocks anything leaving the local
 * server. Aborted off-origin requests are kept apart from `problems`: the abort
 * is this suite's doing, and folding it in would mask the page defects the
 * `problems` list exists to surface.
 */
async function watchPage(page: Page, baseUrl: string): Promise<Watch> {
  const problems: string[] = [];
  const external: string[] = [];
  // Compared by origin rather than string prefix: `http://127.0.0.1:4173@evil.test/`
  // starts with the base URL but resolves to `evil.test`, so a prefix test would
  // wave through the very thing this guard exists to catch. Anything unparseable
  // counts as off-origin too.
  const baseOrigin = new URL(baseUrl).origin;
  const isLocal = (url: string) => {
    try {
      return new URL(url).origin === baseOrigin;
    } catch {
      return false;
    }
  };

  page.on('console', (message) => {
    if (message.type() === 'error') problems.push(`console error: ${message.text()}`);
  });
  page.on('pageerror', (error) => problems.push(`uncaught: ${error.message}`));
  page.on('requestfailed', (request) => {
    if (!isLocal(request.url())) return;
    problems.push(
      `request failed: ${request.url()} (${request.failure()?.errorText ?? 'unknown'})`,
    );
  });

  await page.route('**/*', async (route, request) => {
    if (isLocal(request.url())) {
      await route.continue();
      return;
    }
    external.push(request.url());
    await route.abort();
  });

  return { problems, external };
}

/**
 * The macro tabs the manifest implies. Compared as a set, so this stays clear
 * of `macro_order`, which only decides their order; umbrella parents are
 * applied because they change *which* tabs reach the top bar.
 */
function expectedMacroTabs(manifest: Manifest): string[] {
  const parents = manifest.macro_parents ?? {};
  const macros = Object.values(manifest.orgs).flatMap((org) => [
    ...(org.sections ?? []).map((section) => section.macro),
    ...(org.chart_sections ?? []).map((section) => section.macro),
    ...(org.views ?? []).map((view) => view.macro),
  ]);
  return [...new Set(macros.map((name) => parents[name] ?? name))].sort();
}

/** The org the app shows by default: the manifest's first. */
const DEFAULT_ORG = Object.values(MANIFEST.orgs)[0];

const smoke = test.extend<{ watched: Watch }>({
  watched: [
    async ({ page, baseURL }, use) => {
      expect(baseURL, 'playwright.config.ts must set a baseURL').toBeTruthy();
      const watched = await watchPage(page, baseURL as string);
      await use(watched);
      expect(watched.external, 'the suite must never reach off the local server').toEqual([]);
      expect(watched.problems, 'the dashboard must run with a clean console').toEqual([]);
    },
    { auto: true },
  ],
});

smoke('boots and renders every macro tab the manifest lists', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'Hiero — analytics dashboard' })).toBeVisible();

  const macroBar = page.locator('nav.macrobar');
  const expected = expectedMacroTabs(MANIFEST);
  expect(
    await macroBar
      .getByRole('button')
      .allInnerTexts()
      .then((names) => names.sort()),
  ).toEqual(expected);

  for (const name of expected) {
    // Matched on the accessible name rather than a built regex: macro names
    // come from the manifest, and one containing `.` or `(` would otherwise
    // match the wrong tab — exactly the drift this test is meant to notice.
    await macroBar.getByRole('button', { name, exact: true }).click();
    await expect(macroBar.locator('button.active')).toHaveText(name);
    // A tab has rendered once it shows a content card — table, chart or view —
    // or the manifest's note explaining why this org has none. A blank tab
    // satisfies neither. Matching on `.card` rather than the group wrapper is
    // deliberate: `SectionGroups` drops the wrapper when a tab has one group.
    await expect(page.locator('.card, p.empty').first()).toBeVisible();
  }
});

smoke('fetches a section over the real API path and renders its rows', async ({ page }) => {
  const section = (DEFAULT_ORG.sections ?? []).find((ref) => ref.row_count > 0);
  expect(section, 'the fixture needs a section with rows').toBeDefined();

  await page.goto('/');
  await page
    .locator('nav.macrobar')
    .getByRole('button', { name: section!.macro, exact: true })
    .click();

  // The virtualiser brackets the visible window with two aria-hidden spacer
  // rows; those are layout, not data.
  const rows = page.locator(`table tbody tr:not([aria-hidden="true"])`);
  await expect(rows.first()).toBeVisible();
  expect(await rows.count()).toBeGreaterThan(0);
});

smoke('opens and closes the chart lightbox', async ({ page }) => {
  const chartSection = (DEFAULT_ORG.chart_sections ?? [])[0];
  expect(chartSection, 'the fixture needs a chart section').toBeDefined();
  const title = chartSection.charts[0].title;

  await page.goto('/');
  await page
    .locator('nav.macrobar')
    .getByRole('button', { name: chartSection.macro, exact: true })
    .click();

  const lightbox = page.getByRole('dialog', { name: title });
  await expect(lightbox).toBeHidden();

  await page.getByRole('img', { name: title }).click();
  await expect(lightbox).toBeVisible();
  // The enlarged chart is the point of opening it, so assert the image is
  // really there rather than just the overlay.
  await expect(lightbox.getByRole('img', { name: title })).toBeVisible();

  await page.keyboard.press('Escape');
  await expect(lightbox).toBeHidden();
});
