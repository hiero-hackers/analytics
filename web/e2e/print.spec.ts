import type { Page } from '@playwright/test';
import { PRINT_CONTRIB_DOC, PRINT_GOV_DOC } from './fixtures';
import { MATRIX_DOC } from '../src/test/fixtures';
import { test, expect } from './browser';

async function enterNativePrint(page: Page) {
  await page.evaluate(() => window.dispatchEvent(new Event('beforeprint')));
  await page.emulateMedia({ media: 'print' });
  await expect(page.locator('html')).toHaveAttribute('data-printing', 'true');
}

async function leavePrint(page: Page) {
  await page.emulateMedia({ media: 'screen' });
  await page.evaluate(() => window.dispatchEvent(new Event('afterprint')));
  await expect(page.locator('html')).not.toHaveAttribute('data-printing', 'true');
}

async function openGovernance(page: Page) {
  await page.goto('./#tab=Governance');
  await expect(page.locator('#roles')).toBeVisible();
}

async function decodedCharts(page: Page) {
  await expect
    .poll(() =>
      page.locator('figure img').evaluateAll((images) =>
        images.every((image) => {
          const img = image as HTMLImageElement;
          return img.complete && img.naturalWidth > 0;
        }),
      ),
    )
    .toBe(true);
}

async function observePrintDialog(page: Page) {
  await page.addInitScript(() => {
    const observed = window as unknown as Window & {
      printObservations: { imagesReady: boolean; rowCount: number }[];
    };
    observed.printObservations = [];
    window.print = () => {
      observed.printObservations.push({
        imagesReady: [...document.querySelectorAll<HTMLImageElement>('figure img')].every(
          (image) => image.complete && image.naturalWidth > 0,
        ),
        rowCount: document.querySelectorAll('#roles tbody tr').length,
      });
    };
  });
}

const printCalls = (page: Page) =>
  page.evaluate(
    () =>
      (
        window as unknown as Window & {
          printObservations: { imagesReady: boolean; rowCount: number }[];
        }
      ).printObservations,
  );

test('native printing renders every virtualised row, opens sections, and restores screen state', async ({
  page,
  browserErrors,
}) => {
  await openGovernance(page);
  const rows = page.locator('#roles tbody tr');
  expect(await rows.count()).toBeLessThan(PRINT_GOV_DOC.rows.length);
  const group = page.locator('details.group').last();
  await group.locator(':scope > summary').click();
  await expect(group).not.toHaveAttribute('open', '');

  await enterNativePrint(page);
  await expect(rows).toHaveCount(PRINT_GOV_DOC.rows.length);
  await expect(page.getByRole('cell', { name: 'member-125', exact: true })).toBeVisible();
  await expect(page.locator('#roles')).toBeVisible();
  await expect(page.locator('#pipeline figure')).toHaveCount(2);
  await decodedCharts(page);

  await leavePrint(page);
  await expect(group).not.toHaveAttribute('open', '');
  await group.locator(':scope > summary').click();
  await expect.poll(() => rows.count()).toBeLessThan(PRINT_GOV_DOC.rows.length);
  expect(browserErrors).toEqual([]);
});

test('print media hides controls, uses light colours, and keeps long cells inside the page', async ({
  page,
  browserErrors,
  browserName,
}, testInfo) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await openGovernance(page);
  await enterNativePrint(page);
  await decodedCharts(page);

  for (const locator of [
    page.locator('nav'),
    page.locator('.jump'),
    page.getByRole('button', { name: 'Copy link', includeHidden: true }),
    page.getByRole('button', { name: 'Download CSV', includeHidden: true }),
    page.getByRole('textbox', { name: 'Filter rows', includeHidden: true }),
    page.getByRole('group', { name: 'Time range', includeHidden: true }),
  ]) {
    for (const element of await locator.all()) await expect(element).toBeHidden();
  }
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(255, 255, 255)');
  for (const img of await page.locator('figure img').all()) {
    await expect(img).toHaveCSS('filter', 'none');
  }
  await expect(page.locator('#roles tbody td').last()).toHaveCSS('white-space', 'normal');
  const width = await page.locator('#roles').evaluate((section) => {
    const bounds = section.getBoundingClientRect();
    return [...section.querySelectorAll('th, td')].every((cell) => {
      const rect = cell.getBoundingClientRect();
      return rect.left >= bounds.left - 1 && rect.right <= bounds.right + 1;
    });
  });
  expect(width).toBe(true);
  const stamp = await page
    .locator('html')
    .evaluate((element) => getComputedStyle(element).getPropertyValue('--print-provenance'));
  expect(stamp).toContain('abc1234');
  expect(stamp).toContain('2026-07-25 21:00');

  if (browserName === 'chromium') {
    // Keep an actual multi-page artifact for reviewing table continuation,
    // running provenance/page counters, wrapping, and chart placement.
    const path = testInfo.outputPath('governance.pdf');
    await page.pdf({ path, preferCSSPageSize: true, printBackground: true });
    await testInfo.attach('governance.pdf', { path, contentType: 'application/pdf' });
  }
  expect(browserErrors).toEqual([]);
});

test('large tables print a deliberate row cap and an explicit omission notice', async ({
  page,
}) => {
  await page.goto('./#tab=Contributors');
  await expect(page.locator('#profiles')).toBeVisible();
  await enterNativePrint(page);
  const printed = await page.locator('#profiles tbody tr').count();
  expect(printed).toBe(500);
  expect(printed).toBeLessThan(PRINT_CONTRIB_DOC.row_count);
  await expect(page.locator('#profiles')).toContainText(/500.*620/);
  await expect(page.locator('#profiles')).toContainText(/omitted|truncated|remaining|not printed/i);
  await expect(page.getByRole('cell', { name: 'contributor-0500', exact: true })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'contributor-0501', exact: true })).toHaveCount(0);
});

test('print-media emulation alone switches off virtualisation', async ({ page }) => {
  await openGovernance(page);
  await page.emulateMedia({ media: 'print' });
  await expect(page.locator('html')).toHaveAttribute('data-printing', 'true');
  await expect(page.locator('#roles tbody tr')).toHaveCount(PRINT_GOV_DOC.row_count);
  await page.emulateMedia({ media: 'screen' });
  await expect(page.locator('html')).not.toHaveAttribute('data-printing', 'true');
});

test('a page opened with print media active prepares all rows and slideshow charts', async ({
  page,
}) => {
  await page.emulateMedia({ media: 'print' });
  await page.goto('./#tab=Governance');
  await expect(page.locator('#roles')).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-printing', 'true');
  await expect(page.locator('#pipeline figure').nth(1)).toBeVisible();
  await expect(page.locator('#roles tbody tr')).toHaveCount(PRINT_GOV_DOC.row_count);
});

test('printing respects the selected period and keeps its label after hiding tabs', async ({
  page,
}) => {
  await openGovernance(page);
  const section = page.locator('#roles');
  await section.getByRole('button', { name: '1 month', exact: true }).click();
  await expect(section.getByRole('cell', { name: 'alice', exact: true })).toBeVisible();
  await enterNativePrint(page);
  await expect(section.locator('tbody tr')).toHaveCount(1);
  await expect(section.getByRole('cell', { name: 'alice', exact: true })).toBeVisible();
  await expect(section.getByText('Time range: 1 month', { exact: true })).toBeVisible();
  await expect(section.getByRole('button', { name: '1 month', includeHidden: true })).toBeHidden();
  await leavePrint(page);
  await expect(section.getByRole('button', { name: '1 month', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
});

test('a failed section remains an explicit gap in printed output', async ({ page }) => {
  await page.route('**/data/api/v1/hiero-ledger/roles.json', (route) =>
    route.fulfill({ status: 503, body: 'Unavailable for test' }),
  );
  await page.goto('./#tab=Governance');
  const notice = page.getByText(/Could not load.*Role holders/);
  await expect(notice).toBeVisible();
  await enterNativePrint(page);
  await expect(notice).toBeVisible();
  await expect(page.locator('#pipeline')).toBeVisible();
});

test('native print during a pending data request marks the document incomplete', async ({
  page,
}) => {
  let release: () => void = () => {};
  const pending = new Promise<void>((resolve) => (release = resolve));
  await page.route('**/data/api/v1/hiero-ledger/roles.json', async (route) => {
    await pending;
    await route.continue();
  });
  try {
    await page.goto('./#tab=Governance');
    await expect(page.getByRole('button', { name: 'Print tab', exact: true })).toBeDisabled();
    await enterNativePrint(page);
    await expect(page.getByText(/Incomplete document: this tab is still loading/)).toBeVisible();
  } finally {
    release();
  }
});

test('printing preserves filtered and sorted rows and makes the filter explicit', async ({
  page,
}) => {
  await openGovernance(page);
  const section = page.locator('#roles');
  await section.getByRole('textbox', { name: 'Filter rows' }).fill('member-12');
  await expect(section.locator('tbody tr')).toHaveCount(6);
  await section.getByRole('button', { name: 'count', exact: true }).click();
  const order = await section.locator('tbody tr td:first-child').allTextContents();

  await enterNativePrint(page);
  await expect(section.locator('tbody tr')).toHaveCount(6);
  expect(await section.locator('tbody tr td:first-child').allTextContents()).toEqual(order);
  await expect(section).toContainText(/filter.*member-12/i);
  await leavePrint(page);
  await expect(section.getByRole('textbox', { name: 'Filter rows' })).toHaveValue('member-12');
});

test('the selected role variant remains selected in the printed table', async ({ page }) => {
  await page.goto('./#tab=Diversity');
  const section = page.locator('#affiliations');
  await section.getByRole('button', { name: 'Committers', exact: true }).click();
  await expect(section.getByRole('cell', { name: 'dave', exact: true })).toBeVisible();
  await enterNativePrint(page);
  await expect(section.locator('tbody tr')).toHaveCount(1);
  await expect(section.getByRole('cell', { name: 'dave', exact: true })).toBeVisible();
  await expect(section.getByRole('cell', { name: 'alice', exact: true })).toHaveCount(0);
  await leavePrint(page);
  await expect(section.getByRole('button', { name: 'Committers', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
});

test('Print tab waits for all slideshow charts to decode before opening the dialog', async ({
  page,
  browserErrors,
}) => {
  await observePrintDialog(page);
  let release: () => void = () => {};
  const pending = new Promise<void>((resolve) => (release = resolve));
  let requested: () => void = () => {};
  const started = new Promise<void>((resolve) => (requested = resolve));
  await page.route('**/pipeline_monthly.png', async (route) => {
    requested();
    await pending;
    await route.continue();
  });
  try {
    await page.goto('./#tab=Governance', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('#roles')).toBeVisible();
    await page.getByRole('button', { name: 'Print tab', exact: true }).click();
    await started;
    await expect(page.locator('html')).toHaveAttribute('data-printing', 'true');
    expect(await printCalls(page)).toHaveLength(0);
  } finally {
    release();
  }
  await expect
    .poll(() => printCalls(page))
    .toEqual([{ imagesReady: true, rowCount: PRINT_GOV_DOC.row_count }]);
  await leavePrint(page);
  await expect(page.getByRole('button', { name: 'Print tab', exact: true })).toBeEnabled();
  expect(browserErrors).toEqual([]);
});

test('an unavailable chart stops automatic printing and remains a named native-print warning', async ({
  page,
}) => {
  await observePrintDialog(page);
  await page.route('**/pipeline_monthly.png', (route) =>
    route.fulfill({ status: 503, body: 'Unavailable chart for test' }),
  );
  await openGovernance(page);
  await page.getByRole('button', { name: 'Print tab', exact: true }).click();
  const warning = page.getByText(
    /chart.*unavailable|could not.*chart|chart.*could not|chart.*failed/i,
  );
  await expect(warning.first()).toBeVisible();
  expect(await printCalls(page)).toHaveLength(0);
  await enterNativePrint(page);
  await expect(page.locator('#pipeline')).toContainText(/unavailable|could not|failed/i);
  await expect(page.locator('#roles tbody tr')).toHaveCount(PRINT_GOV_DOC.row_count);
});

test('changing tabs cancels pending print preparation instead of printing the new tab', async ({
  page,
}) => {
  await observePrintDialog(page);
  let release: () => void = () => {};
  const pending = new Promise<void>((resolve) => (release = resolve));
  await page.route('**/pipeline_monthly.png', async (route) => {
    await pending;
    await route.continue();
  });
  try {
    await page.goto('./#tab=Governance', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('#roles')).toBeVisible();
    await page.getByRole('button', { name: 'Print tab', exact: true }).click();
    await expect(page.locator('html')).toHaveAttribute('data-printing', 'true');
    await page.getByRole('button', { name: 'Contributors', exact: true }).click();
    await expect(page.locator('#profiles')).toBeVisible();
    await expect(page.locator('html')).not.toHaveAttribute('data-printing', 'true');
    expect(await printCalls(page)).toHaveLength(0);
  } finally {
    release();
  }
  // The old image can still finish after its component unmounts. Let that
  // response and rendering frame settle before checking for a stale dialog.
  await page.waitForLoadState('load');
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));
  expect(await printCalls(page)).toHaveLength(0);
  await expect(page.getByRole('button', { name: 'Print tab', exact: true })).toBeEnabled();
});

test('native print restores keyboard focus to period, sort, KPI and role controls', async ({
  page,
}) => {
  await openGovernance(page);
  for (const control of [
    page.locator('#roles').getByRole('button', { name: '1 month', exact: true }),
    page.locator('#roles').getByRole('button', { name: 'count', exact: true }),
    page.getByRole('button', { name: /maintainers 103/i }),
  ]) {
    await control.focus();
    await expect(control).toBeFocused();
    await enterNativePrint(page);
    await leavePrint(page);
    await expect(control).toBeFocused();
  }
  await page.getByRole('button', { name: 'Diversity', exact: true }).click();
  const role = page
    .locator('#affiliations')
    .getByRole('button', { name: 'Committers', exact: true });
  await role.focus();
  await expect(role).toBeFocused();
  await enterNativePrint(page);
  await leavePrint(page);
  await expect(role).toBeFocused();
});

test('native print preserves horizontal and vertical matrix scrolling', async ({ page }) => {
  const columns = Array.from({ length: 14 }, (_, index) => ({
    key: `repo-${index}`,
    label: `component-${index}`,
    band: 'Components',
  }));
  const matrix = {
    ...MATRIX_DOC,
    columns,
    bands: [{ label: 'Components', span: columns.length }],
    rows: Array.from({ length: 100 }, (_, index) => ({
      ...MATRIX_DOC.rows[0],
      key: 1200 + index,
      label: `HIP-${1200 + index}`,
      cells: columns.map(({ key }) => ({ key, merged: 1, open: 0 })),
    })),
  };
  await page.route('**/hip-matrix.json', (route) => route.fulfill({ json: matrix }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('./#tab=HIPs');
  const scroller = page.locator('.hipmx-wrap');
  await scroller.scrollIntoViewIfNeeded();
  await scroller.evaluate((element) => {
    element.scrollTop = 700;
    element.scrollLeft = 200;
  });
  const offset = () =>
    scroller.evaluate((element) => ({ top: element.scrollTop, left: element.scrollLeft }));
  await expect.poll(offset).toEqual({ top: 700, left: 200 });
  await enterNativePrint(page);
  await expect(page.locator('[data-print-matrix] tbody tr')).toHaveCount(100);
  await leavePrint(page);
  await expect.poll(offset).toEqual({ top: 700, left: 200 });
});
