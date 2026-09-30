import type { Page } from '@playwright/test';
import { ENTITY_ROUTES } from '../src/test/entityFixtures';
import { test, expect } from './browser';

/** Serve the entity fixtures over the staged site's manifest and API tree. */
async function serveEntities(page: Page) {
  // The component suite's role table (alice, bob, carol) rather than the print suite's large one.
  const served = new Set(['manifest.json', 'hiero-ledger/roles.json']);
  for (const [path, body] of Object.entries(ENTITY_ROUTES)) {
    if (!served.has(path) && !path.includes('/entities/')) continue;
    await page.route(`**/data/api/v1/${path}`, (route) => route.fulfill({ json: body }));
  }
}

test('a table name opens its detail view, and browser history steps through it', async ({
  page,
  browserErrors,
}) => {
  await serveEntities(page);
  await page.goto('./#tab=Governance');
  const roles = page.locator('#roles');
  await roles.getByRole('link', { name: 'alice', exact: true }).click();

  await expect(page.getByRole('heading', { level: 1, name: 'alice' })).toBeVisible();
  await expect(page.getByText(/does not measure commits, comments, reactions/)).toBeVisible();
  await expect(page).toHaveURL(/entity=contributor%3Aalice/);
  await expect(page.getByRole('region', { name: 'Activity by period' })).toBeVisible();

  // The repository in alice's list opens that repository: a second history entry.
  await page
    .getByRole('region', { name: 'Repositories' })
    .getByRole('link', { name: 'hiero-ledger/hiero-sdk-js', exact: true })
    .click();
  await expect(page.getByRole('heading', { level: 1, name: 'hiero-sdk-js' })).toBeVisible();
  await expect(
    page.getByText('Not available in this data: Security.', { exact: false }),
  ).toBeVisible();

  await page.goBack();
  await expect(page.getByRole('heading', { level: 1, name: 'alice' })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole('heading', { level: 1, name: 'Governance' })).toBeVisible();
  await expect(roles).toBeVisible();
  await page.goForward();
  await expect(page.getByRole('heading', { level: 1, name: 'alice' })).toBeVisible();
  expect(browserErrors).toEqual([]);
});

test('a detail view prints as a document, without navigation or controls', async ({ page }) => {
  await serveEntities(page);
  await page.goto('./#tab=Governance&entity=repo:hiero-sdk-js');
  await expect(page.getByRole('region', { name: 'Activity by period' })).toBeVisible();
  await page.evaluate(() => window.dispatchEvent(new Event('beforeprint')));
  await page.emulateMedia({ media: 'print' });
  await expect(page.locator('html')).toHaveAttribute('data-printing', 'true');

  await expect(page.getByRole('heading', { level: 1, name: 'hiero-sdk-js' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Active contributors' })).toBeVisible();
  for (const control of [
    page.getByRole('link', { name: /Back to Governance/, includeHidden: true }),
    page.getByRole('button', { name: 'Print page', includeHidden: true }),
    page.locator('[data-slot="sidebar"]'),
  ]) {
    for (const element of await control.all()) await expect(element).toBeHidden();
  }
  await page.emulateMedia({ media: 'screen' });
  await page.evaluate(() => window.dispatchEvent(new Event('afterprint')));
});

test('a figure on a repository view links back to its section, landing on it', async ({ page }) => {
  await serveEntities(page);
  await page.goto('./#tab=Contributors&entity=repo:hiero-sdk-js');
  await page
    .getByRole('region', { name: 'HIP engagement' })
    .getByRole('link', { name: /Role holders/ })
    .click();
  const roles = page.locator('#roles');
  await expect(page).toHaveURL(/tab=Governance&.*widget=roles|widget=roles&.*tab=Governance/);
  await expect(page.getByRole('heading', { level: 1, name: 'Governance' })).toBeVisible();
  // Held in place while the charts above it load, then left to the reader.
  await expect(roles).toBeInViewport();
  await page.waitForTimeout(1500);
  await expect(roles).toBeInViewport();
});
