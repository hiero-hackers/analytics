import { MANIFEST } from '../src/test/fixtures';
import { test, expect } from './browser';

test('the built app boots offline under a subpath and each macro renders', async ({
  page,
  browserErrors,
}) => {
  await page.goto('./');
  await expect(page.getByRole('heading', { name: 'Hiero — analytics dashboard' })).toBeVisible();
  const macros = new Set(
    Object.values(MANIFEST.orgs).flatMap((entry) => [
      ...entry.sections.map((section) => section.macro),
      ...entry.chart_sections.map((section) => section.macro),
      ...(entry.views ?? []).map((view) => view.macro),
    ]),
  );
  for (const macro of macros) {
    await page.getByRole('button', { name: macro, exact: true }).click();
    await expect(page.getByRole('table').first()).toBeVisible();
    await expect(page.getByRole('table').first().locator('tbody tr').first()).toBeVisible();
  }
  await page.getByRole('button', { name: 'Governance', exact: true }).click();
  const chart = page.getByRole('img', { name: 'Unique active contributors by role' });
  await chart.click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(browserErrors).toEqual([]);
});
