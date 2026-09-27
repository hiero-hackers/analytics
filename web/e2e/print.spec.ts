import type { Locator, Page } from '@playwright/test';
import {
  PIPELINE_DOCS,
  PRINT_CONTRIB_DOC,
  PRINT_GOV_DOC,
  PRINT_MANIFEST,
  pipelineDocument,
} from './fixtures';
import { BOARD_DOC, HIP_EVIDENCE_DOC, MATRIX_DOC } from '../src/test/fixtures';
import { test, expect } from './browser';

const CHART = 'Unique active contributors by role';
const NEXT_CHART = 'The next pipeline chart';

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

/** A tab in the sidebar's page list. */
const tab = (page: Page, name: string) =>
  page.getByRole('navigation', { name: 'Dashboard' }).getByRole('button', { name, exact: true });

async function setScrollOffset(scroller: Locator, top: number, left: number) {
  await scroller.evaluate(
    (element, offset) => {
      element.scrollTop = offset.top;
      element.scrollLeft = offset.left;
    },
    { top, left },
  );
}

const scrollOffset = (scroller: Locator) =>
  scroller.evaluate((element) => ({
    top: Math.round(element.scrollTop),
    left: Math.round(element.scrollLeft),
  }));

/** Per pipeline figure: whether its Recharts SVG is laid out and has drawn bars. */
const drawnCharts = (page: Page) =>
  page.locator('#pipeline figure').evaluateAll((figures) =>
    figures.map((figure) => {
      const svg = figure.querySelector('[data-slot="chart"] svg.recharts-surface');
      const box = svg?.getBoundingClientRect();
      return Boolean(
        box && box.width > 0 && box.height > 0 && svg!.querySelector('.recharts-bar-rectangle'),
      );
    }),
  );

/** Both slides printed as drawn charts: nothing still loading, nothing failed. */
async function chartsReady(page: Page) {
  await expect(page.locator('[data-print-pending]')).toHaveCount(0);
  await expect(page.locator('[data-print-error]')).toHaveCount(0);
  await expect.poll(() => drawnCharts(page)).toEqual([true, true]);
}

interface PrintObservation {
  pending: number;
  failed: number;
  drawn: number;
  rowCount: number;
}

/** Replace the native dialog with a probe of what the document holds when it would open. */
async function observePrintDialog(page: Page) {
  await page.addInitScript(() => {
    const observed = window as unknown as Window & { printObservations: PrintObservation[] };
    observed.printObservations = [];
    window.print = () => {
      observed.printObservations.push({
        pending: document.querySelectorAll('[data-print-pending]').length,
        failed: document.querySelectorAll('[data-print-error]').length,
        drawn: [...document.querySelectorAll('#pipeline figure')].filter((figure) => {
          const svg = figure.querySelector('[data-slot="chart"] svg.recharts-surface');
          const box = svg?.getBoundingClientRect();
          return (
            box && box.width > 0 && box.height > 0 && svg!.querySelector('.recharts-bar-rectangle')
          );
        }).length,
        rowCount: document.querySelectorAll('#roles tbody tr').length,
      });
    };
  });
}

const printCalls = (page: Page) =>
  page.evaluate(
    () =>
      (window as unknown as Window & { printObservations: PrintObservation[] }).printObservations,
  );

/** Hold one chart document's response until the returned release is called. */
async function holdChart(page: Page, file: string) {
  let release: () => void = () => {};
  const pending = new Promise<void>((resolve) => (release = resolve));
  let requested: () => void = () => {};
  const started = new Promise<void>((resolve) => (requested = resolve));
  await page.route(`**/data/api/v1/hiero-ledger/charts/${file}`, async (route) => {
    requested();
    await pending;
    await route.continue();
  });
  return { release, started };
}

test('native printing renders every virtualised row, opens sections, and restores screen state', async ({
  page,
  browserErrors,
}) => {
  await openGovernance(page);
  const rows = page.locator('#roles tbody tr');
  expect(await rows.count()).toBeLessThan(PRINT_GOV_DOC.rows.length);
  // The reader folds a whole group, one card, and leaves the glossary folded.
  // The group's own trigger, not the sidebar's table-of-contents entry of the same name.
  const groupToggle = page
    .locator('[data-slot="collapsible-trigger"]')
    .filter({ hasText: 'Roles & teams' });
  const group = groupToggle.locator('xpath=..');
  await groupToggle.click();
  await expect(group).toHaveAttribute('data-state', 'closed');
  await expect(page.locator('#roles')).toHaveCount(0);
  await page.getByRole('button', { name: 'Collapse Maintainer pipeline', exact: true }).click();
  await expect(page.locator('#pipeline figure')).toHaveCount(0);
  const glossary = page.getByText('pull requests opened;');
  await expect(glossary).toBeHidden();

  await enterNativePrint(page);
  await expect(page.locator('h2.print-group')).toHaveText(['Pipeline charts', 'Roles & teams']);
  await expect(rows).toHaveCount(PRINT_GOV_DOC.rows.length);
  await expect(page.getByRole('cell', { name: 'member-125', exact: true })).toBeVisible();
  await expect(page.locator('#roles')).toBeVisible();
  await expect(page.locator('#pipeline figure')).toHaveCount(2);
  await chartsReady(page);
  // The explanations under each chart print open, as does the glossary.
  await expect(page.locator('#pipeline').getByText('Resolve roles per bucket.')).toHaveCount(2);
  for (const step of await page.locator('#pipeline').getByText('Resolve roles per bucket.').all()) {
    await expect(step).toBeVisible();
  }
  await expect(glossary).toBeVisible();

  await leavePrint(page);
  await expect(group).toHaveAttribute('data-state', 'closed');
  await expect(page.locator('#roles')).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: 'Expand Maintainer pipeline', exact: true }),
  ).toBeVisible();
  await expect(page.locator('#pipeline figure')).toHaveCount(0);
  await expect(glossary).toBeHidden();
  await groupToggle.click();
  await expect(page.locator('#roles')).toBeVisible();
  await expect.poll(() => rows.count()).toBeLessThan(PRINT_GOV_DOC.rows.length);
  expect(browserErrors).toEqual([]);
});

// The chart palette tokens (src/app.css) in each scheme, as computed colours.
const LIGHT_SERIES = [
  'rgb(100, 116, 139)',
  'rgb(183, 121, 19)',
  'rgb(22, 133, 117)',
  'rgb(57, 117, 220)',
];
const DARK_SERIES = [
  'rgb(148, 163, 184)',
  'rgb(233, 180, 76)',
  'rgb(61, 197, 173)',
  'rgb(121, 168, 250)',
];
const barFills = (page: Page) =>
  page
    .locator('#pipeline [data-slot="chart"] .recharts-bar-rectangle path')
    .evaluateAll((paths) => [...new Set(paths.map((path) => getComputedStyle(path).fill))].sort());

test('print media hides controls, uses light colours, and keeps long cells inside the page', async ({
  page,
  browserErrors,
  browserName,
}, testInfo) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await openGovernance(page);
  await expect.poll(() => barFills(page)).toEqual([...DARK_SERIES].sort());
  await enterNativePrint(page);
  await chartsReady(page);

  for (const locator of [
    page.locator('header'),
    page.locator('[data-slot="sidebar"]'),
    page.getByRole('button', { name: 'Print tab', includeHidden: true }),
    page.getByRole('button', { name: 'Copy link', includeHidden: true }),
    page.getByRole('button', { name: 'Download CSV', includeHidden: true }),
    page.getByRole('button', { name: /^Expand interactive chart/, includeHidden: true }),
    page.getByRole('textbox', { name: 'Filter rows', includeHidden: true }),
    // Single-select toggle groups are radiogroups.
    page.getByRole('radiogroup', { name: 'Time range', includeHidden: true }),
    page.getByRole('radiogroup', { name: `${CHART} view`, includeHidden: true }),
  ]) {
    expect(await locator.count()).toBeGreaterThan(0);
    for (const element of await locator.all()) await expect(element).toBeHidden();
  }
  // Only buttons that carry data (a legend entry, the glossary title) print, as text.
  await expect(page.locator('button:not([data-print-keep])').locator('visible=true')).toHaveCount(
    0,
  );
  await expect(page.locator('input').locator('visible=true')).toHaveCount(0);
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(255, 255, 255)');
  await expect(page.locator('body')).toHaveCSS('color', 'rgb(27, 27, 27)');
  // The charts draw in the light palette even though the reader's screen is dark.
  expect(await barFills(page)).toEqual([...LIGHT_SERIES].sort());
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
  const printed = await page.locator('#profiles tbody tr:not([hidden])').count();
  expect(printed).toBe(500);
  expect(printed).toBeLessThan(PRINT_CONTRIB_DOC.row_count);
  const notice = page.locator('#profiles [data-print-truncated]');
  await expect(notice).toBeVisible();
  await expect(notice).toContainText(/500.*620/);
  await expect(notice).toContainText(/omitted|truncated|remaining|not printed/i);
  await expect(page.getByRole('cell', { name: 'contributor-0500', exact: true })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'contributor-0501', exact: true })).toHaveCount(0);
});

test('printing a capped table preserves scrolling and focus beyond the printed rows', async ({
  page,
}) => {
  await page.route('**/profiles.json', (route) =>
    route.fulfill({
      json: {
        ...PRINT_CONTRIB_DOC,
        columns: [...PRINT_CONTRIB_DOC.columns, { key: 'url', label: 'Profile', format: 'link' }],
        rows: PRINT_CONTRIB_DOC.rows.map((row, index) => ({
          ...row,
          url: `https://example.test/profile/${index}`,
        })),
      },
    }),
  );
  await page.goto('./#tab=Contributors');
  const scroller = page.locator('#profiles [data-slot="table-container"]');
  await setScrollOffset(scroller, 100000, 0);
  const link = scroller.locator('a[href="https://example.test/profile/619"]');
  await link.focus();
  await expect(link).toBeFocused();
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
  const offset = await scrollOffset(scroller);
  expect(offset.top).toBeGreaterThan(14000);
  await enterNativePrint(page);
  await expect(page.locator('#profiles tbody tr:not([hidden])')).toHaveCount(500);
  await expect(link).toBeHidden();
  await expect(page.getByRole('cell', { name: 'contributor-0620', exact: true })).toHaveCount(0);
  await leavePrint(page);
  await expect.poll(() => scrollOffset(scroller)).toEqual(offset);
  await expect(link).toBeFocused();
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
  await expect(page.getByRole('figure', { name: `${NEXT_CHART} — By month` })).toBeVisible();
  await expect(page.locator('#roles tbody tr')).toHaveCount(PRINT_GOV_DOC.row_count);
  await chartsReady(page);
});

test('printing respects the selected period and keeps its label after hiding tabs', async ({
  page,
}) => {
  await openGovernance(page);
  const section = page.locator('#roles');
  const month = section.getByRole('radio', { name: '1 month', exact: true });
  await month.click();
  await expect(section.getByRole('cell', { name: 'alice', exact: true })).toBeVisible();
  await enterNativePrint(page);
  await expect(section.locator('tbody tr')).toHaveCount(1);
  await expect(section.getByRole('cell', { name: 'alice', exact: true })).toBeVisible();
  await expect(section.getByText('Time range: 1 month', { exact: true })).toBeVisible();
  await expect(section.getByRole('radio', { name: '1 month', includeHidden: true })).toBeHidden();
  await leavePrint(page);
  await expect(month).toHaveAttribute('aria-checked', 'true');
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
  await expect(section.getByRole('columnheader', { name: 'count' })).toHaveAttribute(
    'aria-sort',
    /ascending|descending/,
  );
  const order = await section.locator('tbody tr td:first-child').allTextContents();

  await enterNativePrint(page);
  await expect(section.locator('tbody tr')).toHaveCount(6);
  expect(await section.locator('tbody tr td:first-child').allTextContents()).toEqual(order);
  await expect(section).toContainText(/filter.*member-12/i);
  // The header keeps its label on paper while the sort button is hidden.
  await expect(section.getByRole('columnheader', { name: 'count' })).toBeVisible();
  await expect(section.getByRole('button', { name: 'count', includeHidden: true })).toBeHidden();
  await leavePrint(page);
  await expect(section.getByRole('textbox', { name: 'Filter rows' })).toHaveValue('member-12');

  await section.getByRole('textbox', { name: 'Filter rows' }).fill('no matching contributor');
  const clear = section.getByRole('button', { name: 'clear the filter?' });
  await clear.focus();
  await enterNativePrint(page);
  await expect(section).toContainText('No rows match this filter.');
  await expect(clear).toBeHidden();
  await leavePrint(page);
  await expect(clear).toBeFocused();
  await clear.click();
  await expect(section.getByRole('textbox', { name: 'Filter rows' })).toHaveValue('');
});

test('the selected role variant remains selected in the printed table', async ({ page }) => {
  await page.goto('./#tab=Diversity');
  const section = page.locator('#affiliations');
  const committers = section.getByRole('radio', { name: 'Committers', exact: true });
  await committers.click();
  await expect(section.getByRole('cell', { name: 'dave', exact: true })).toBeVisible();
  await enterNativePrint(page);
  await expect(section.locator('tbody tr')).toHaveCount(1);
  await expect(section.getByRole('cell', { name: 'dave', exact: true })).toBeVisible();
  await expect(section.getByRole('cell', { name: 'alice', exact: true })).toHaveCount(0);
  await expect(section.getByText('Role: Committers', { exact: true })).toBeVisible();
  await leavePrint(page);
  await expect(committers).toHaveAttribute('aria-checked', 'true');
});

test('the selected chart variant is the one printed, and says so', async ({ page }) => {
  await openGovernance(page);
  const pipeline = page.locator('#pipeline');
  const month = pipeline.getByRole('radio', { name: 'By month', exact: true });
  await month.click();
  await expect(page.getByRole('figure', { name: `${CHART} — By month` })).toBeVisible();
  await enterNativePrint(page);
  await chartsReady(page);
  await expect(page.getByRole('figure', { name: `${CHART} — By month` })).toBeVisible();
  await expect(page.getByRole('figure', { name: `${CHART} — By year` })).toHaveCount(0);
  await expect(pipeline.getByText(`${CHART} view: By month`, { exact: true })).toBeVisible();
  await leavePrint(page);
  await expect(month).toHaveAttribute('aria-checked', 'true');
});

test('Print tab waits for every slideshow chart to load before opening the dialog', async ({
  page,
  browserErrors,
}) => {
  await observePrintDialog(page);
  // The second slide is off-screen: its data still has to arrive before printing.
  const next = await holdChart(page, 'pipeline_next.json');
  try {
    await page.goto('./#tab=Governance', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('#roles')).toBeVisible();
    await next.started;
    await page.getByRole('button', { name: 'Print tab', exact: true }).click();
    await expect(page.locator('html')).toHaveAttribute('data-printing', 'true');
    await expect(page.getByRole('status').getByText('Loading charts for printing…')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Preparing print…' })).toBeDisabled();
    await expect(
      page
        .getByRole('figure', { name: `${NEXT_CHART} — By month` })
        .locator('[data-print-pending]'),
    ).toBeVisible();
    expect(await printCalls(page)).toHaveLength(0);
  } finally {
    next.release();
  }
  await expect
    .poll(() => printCalls(page))
    .toEqual([{ pending: 0, failed: 0, drawn: 2, rowCount: PRINT_GOV_DOC.row_count }]);
  await leavePrint(page);
  await expect(page.getByRole('button', { name: 'Print tab', exact: true })).toBeEnabled();
  expect(browserErrors).toEqual([]);
});

test('an unavailable chart stops automatic printing and remains a named native-print warning', async ({
  page,
}) => {
  await observePrintDialog(page);
  await page.route('**/data/api/v1/hiero-ledger/charts/pipeline_yearly.json', (route) =>
    route.fulfill({ status: 503, body: 'Unavailable chart for test' }),
  );
  await openGovernance(page);
  const failed = page
    .locator('#pipeline')
    .getByRole('alert')
    .filter({ hasText: `Could not load chart data: ${CHART} (By year).` });
  await expect(failed).toBeVisible();
  await page.getByRole('button', { name: 'Print tab', exact: true }).click();
  await expect(page.getByText('Could not prepare every chart for printing.')).toBeVisible();
  await expect(page.locator('html')).not.toHaveAttribute('data-printing', 'true');
  expect(await printCalls(page)).toHaveLength(0);
  await enterNativePrint(page);
  await expect(failed).toBeVisible();
  await expect(page.getByRole('button', { name: 'Retry chart', includeHidden: true })).toBeHidden();
  await expect(page.locator('#roles tbody tr')).toHaveCount(PRINT_GOV_DOC.row_count);
});

test('changing tabs cancels pending print preparation instead of printing the new tab', async ({
  page,
}) => {
  await observePrintDialog(page);
  const next = await holdChart(page, 'pipeline_next.json');
  try {
    await page.goto('./#tab=Governance', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('#roles')).toBeVisible();
    await page.getByRole('button', { name: 'Print tab', exact: true }).click();
    await expect(page.locator('html')).toHaveAttribute('data-printing', 'true');
    await tab(page, 'Contributors').click();
    await expect(page.locator('#profiles')).toBeVisible();
    await expect(page.locator('html')).not.toHaveAttribute('data-printing', 'true');
    expect(await printCalls(page)).toHaveLength(0);
  } finally {
    next.release();
  }
  // The old chart request can still finish after its component unmounts. Let
  // that response and a rendering frame settle before checking for a stale dialog.
  await page.waitForLoadState('load');
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));
  expect(await printCalls(page)).toHaveLength(0);
  await expect(page.getByRole('button', { name: 'Print tab', exact: true })).toBeEnabled();
});

test('native print restores keyboard focus to period, sort, chart, KPI and role controls', async ({
  page,
}) => {
  await openGovernance(page);
  for (const control of [
    page.locator('#roles').getByRole('radio', { name: '1 month', exact: true }),
    page.locator('#roles').getByRole('button', { name: 'count', exact: true }),
    page.locator('#pipeline').getByRole('radio', { name: 'By month', exact: true }),
    page.getByRole('button', { name: /maintainers 103/i }),
  ]) {
    await control.focus();
    await expect(control).toBeFocused();
    await enterNativePrint(page);
    await leavePrint(page);
    await expect(control).toBeFocused();
  }
  await tab(page, 'Diversity').click();
  const role = page
    .locator('#affiliations')
    .getByRole('radio', { name: 'Committers', exact: true });
  await role.focus();
  await expect(role).toBeFocused();
  await enterNativePrint(page);
  await leavePrint(page);
  await expect(role).toBeFocused();
});

test('native print preserves table, chart-data and period-tab scrolling', async ({ page }) => {
  // Enough windows that the period tabs overflow and scroll at phone width.
  const periods = {
    '7d': '1 week',
    '14d': '2 weeks',
    '30d': '1 month',
    '90d': '3 months',
    '180d': '6 months',
    '365d': '1 year',
    '730d': '2 years',
  };
  await page.route('**/manifest.json', (route) =>
    route.fulfill({ json: { ...PRINT_MANIFEST, period_labels: periods } }),
  );
  await page.route('**/hiero-ledger/roles.json', (route) =>
    route.fulfill({
      json: {
        ...PRINT_GOV_DOC,
        periods: Object.fromEntries(Object.keys(periods).map((key) => [key, PRINT_GOV_DOC.rows])),
      },
    }),
  );
  // Enough years for the chart's Data view to scroll inside its own box.
  const years = Array.from({ length: 30 }, (_, index) => String(1997 + index));
  await page.route('**/charts/pipeline_yearly.json', (route) =>
    route.fulfill({ json: pipelineDocument('pipeline_yearly', 'year', years) }),
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await openGovernance(page);
  const figure = page.getByRole('figure', { name: `${CHART} — By year` });
  await figure.getByRole('radio', { name: 'Data', exact: true }).click();
  const table = page.locator('#roles [data-slot="table-container"]');
  const chartData = figure.locator('[data-slot="table-container"]');
  const periodTabs = page.locator('#roles').getByRole('radiogroup', { name: 'Time range' });
  await expect(chartData.locator('tbody tr')).toHaveCount(years.length);
  await table.scrollIntoViewIfNeeded();
  await setScrollOffset(table, 600, 200);
  await setScrollOffset(chartData, 300, 100);
  await setScrollOffset(periodTabs, 0, 40);
  const offsets = () => Promise.all([table, chartData, periodTabs].map(scrollOffset));
  const expected = [
    { top: 600, left: 200 },
    { top: 300, left: 100 },
    { top: 0, left: 40 },
  ];
  await expect.poll(offsets).toEqual(expected);

  await enterNativePrint(page);
  await expect(page.locator('#roles tbody tr')).toHaveCount(PRINT_GOV_DOC.row_count);
  await expect(chartData).toHaveCSS('overflow-x', 'visible');
  await expect(chartData.locator('tbody tr')).toHaveCount(years.length);
  await expect(periodTabs).toBeHidden();
  await leavePrint(page);
  await expect.poll(offsets).toEqual(expected);
});

test('native print preserves matrix and nested board scrolling', async ({ page }) => {
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
  await page.route('**/hip-board.json', (route) =>
    route.fulfill({
      json: {
        ...BOARD_DOC,
        columns: BOARD_DOC.columns.map((column, index) =>
          index === 0
            ? {
                ...column,
                items: Array.from({ length: 40 }, (_, item) => ({
                  ...column.items[0],
                  key: 1200 + item,
                  label: `HIP-${1200 + item}`,
                })),
              }
            : column,
        ),
      },
    }),
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('./#tab=HIPs');
  const matrixScroller = page.locator('#hip-matrix .hipmx-wrap');
  const board = page.locator('#hip-board .hipboard');
  const chips = page.locator('#hip-board .hipboard-chips').first();
  await matrixScroller.scrollIntoViewIfNeeded();
  await setScrollOffset(matrixScroller, 700, 200);
  await setScrollOffset(board, 0, 200);
  await setScrollOffset(chips, 100, 0);
  const offsets = () => Promise.all([matrixScroller, board, chips].map(scrollOffset));
  const expected = [
    { top: 700, left: 200 },
    { top: 0, left: 200 },
    { top: 100, left: 0 },
  ];
  await expect.poll(offsets).toEqual(expected);
  await enterNativePrint(page);
  await expect(page.locator('[data-print-matrix] tbody tr')).toHaveCount(100);
  await expect(page.locator('#hip-board [data-print-board]').first().locator('li')).toHaveCount(40);
  await leavePrint(page);
  await expect.poll(offsets).toEqual(expected);
});

test('native print preserves open chart and metric explanations', async ({ page }) => {
  const org = PRINT_MANIFEST.orgs['hiero-ledger'];
  // Long enough that both dialogs scroll, even the explanation's at phone height.
  const methodology = Array.from(
    { length: 40 },
    (_, index) => `Step ${index + 1}: count the matching contributors.`,
  );
  await page.route('**/manifest.json', (route) =>
    route.fulfill({
      json: {
        ...PRINT_MANIFEST,
        orgs: {
          ...PRINT_MANIFEST.orgs,
          'hiero-ledger': {
            ...org,
            metrics: {
              ...org.metrics,
              Governance: org.metrics!.Governance.map((tile) => ({ ...tile, methodology })),
            },
          },
        },
      },
    }),
  );
  const yearly = PIPELINE_DOCS['hiero-ledger/charts/pipeline_yearly.json'];
  await page.route('**/charts/pipeline_yearly.json', (route) =>
    route.fulfill({ json: { ...yearly, methodology } }),
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await openGovernance(page);
  const openers = [
    page
      .getByRole('figure', { name: `${CHART} — By year` })
      .getByRole('button', { name: `Expand interactive chart: ${CHART}` }),
    page.getByRole('button', { name: /maintainers 103/i }),
  ];
  for (const opener of openers) {
    await opener.click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    // The expanded chart explains itself in a <details>; the tile's dialog lists its steps.
    const details = dialog.locator('details');
    if (await details.count()) {
      const summary = details.locator('summary');
      await summary.focus();
      await summary.press('Enter');
      await expect(details).toHaveAttribute('open', '');
    }
    await expect(dialog.getByText('Step 40: count the matching contributors.')).toBeVisible();
    // Focus first: focusing the close button scrolls it (top of the dialog) into view.
    const close = dialog.getByRole('button', { name: 'Close', exact: true });
    await close.focus();
    await setScrollOffset(dialog, 100, 0);
    await expect.poll(() => scrollOffset(dialog)).toEqual({ top: 100, left: 0 });

    await enterNativePrint(page);
    await expect(dialog).toBeHidden();
    // The key that dismisses the print dialog must not also close this one.
    await page.keyboard.press('Escape');
    await leavePrint(page);
    await expect(dialog).toBeVisible();
    if (await details.count()) await expect(details).toHaveAttribute('open', '');
    await expect(close).toBeFocused();
    await expect.poll(() => scrollOffset(dialog)).toEqual({ top: 100, left: 0 });
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
  }
});

test('native print restores an open evidence panel and keeps raw numbers unbroken', async ({
  page,
}) => {
  const rows = Array.from({ length: 40 }, (_, index) => ({
    ...HIP_EVIDENCE_DOC.rows[0],
    pr_number: 1000 + index,
  }));
  await page.route('**/hip-evidence.json', (route) =>
    route.fulfill({
      json: { ...HIP_EVIDENCE_DOC, rows, row_count: rows.length },
    }),
  );
  await page.goto('./#tab=HIPs');
  await page.locator('#hip-matrix').getByRole('button', { name: '3', exact: true }).click();
  const heading = page.getByRole('heading', { name: 'HIP-1200 · hiero-ledger/consensus' });
  const panel = heading.locator('xpath=../..');
  await expect(panel).toBeVisible();
  const list = panel.locator('ol');
  await setScrollOffset(list, 200, 0);
  await expect.poll(() => scrollOffset(list)).toEqual({ top: 200, left: 0 });
  const close = panel.getByRole('button', { name: 'Close', exact: true });
  await close.focus();
  const number = page.locator('#hip-evidence').getByRole('cell', { name: '1000', exact: true });
  await expect(number).toBeVisible();

  await enterNativePrint(page);
  await expect(panel).toBeHidden();
  // Numbers read right-aligned on paper and never wrap mid-figure.
  await expect(number).toHaveCSS('text-align', 'right');
  await expect(number).toHaveCSS('white-space', 'nowrap');
  await page.keyboard.press('Escape');
  await leavePrint(page);
  await expect(panel).toBeVisible();
  await expect(close).toBeFocused();
  await expect.poll(() => scrollOffset(list)).toEqual({ top: 200, left: 0 });
  await page.keyboard.press('Escape');
  await expect(panel).toHaveCount(0);
});
