import { MANIFEST } from '../src/test/fixtures';
import { test, expect } from './browser';

test('the built app boots offline under a subpath and each macro renders', async ({
  page,
  browserErrors,
}) => {
  await page.goto('./');
  await expect(page).toHaveTitle('Hiero — analytics dashboard');
  const pages = page.getByRole('navigation', { name: 'Dashboard' });
  const macros = new Set(
    Object.values(MANIFEST.orgs).flatMap((entry) => [
      ...entry.sections.map((section) => section.macro),
      ...entry.chart_sections.map((section) => section.macro),
      ...(entry.views ?? []).map((view) => view.macro),
    ]),
  );
  for (const macro of macros) {
    await pages.getByRole('button', { name: macro, exact: true }).click();
    await expect(page.getByRole('heading', { level: 1, name: macro, exact: true })).toBeVisible();
    await expect(page.getByRole('table').first()).toBeVisible();
    await expect(page.getByRole('table').first().locator('tbody tr').first()).toBeVisible();
  }
  await pages.getByRole('button', { name: 'Governance', exact: true }).click();
  // Charts draw from their JSON documents with Recharts.
  const figure = page.getByRole('figure', { name: 'Unique active contributors by role — By year' });
  await expect(figure.locator('svg.recharts-surface').first()).toBeVisible();
  await figure
    .getByRole('button', { name: 'Expand interactive chart: Unique active contributors by role' })
    .click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('svg.recharts-surface').first()).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  expect(browserErrors).toEqual([]);
});
