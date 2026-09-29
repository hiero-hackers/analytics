import { readFile } from 'node:fs/promises';
import type { Page } from '@playwright/test';
import type { CategoriesDocument } from '../src/api';
import { PIPELINE_DOCS } from './fixtures';
import { test, expect } from './browser';

const CHART = 'Unique active contributors by role';
const NEXT_CHART = 'The next pipeline chart';
const printButton = (page: Page, title = CHART) =>
  page.getByRole('button', { name: `Print chart: ${title}`, exact: true });
const preview = (page: Page) => page.getByRole('dialog', { name: 'Print preview' });
const sheet = (page: Page) => page.locator('[data-print-sheet]');

/** PDF points (1/72 in) of each paper, as Chromium writes the MediaBox. */
const PAPER_PT = {
  'A4 portrait': [595, 842],
  'A4 landscape': [842, 595],
  'Letter portrait': [612, 792],
  'Letter landscape': [792, 612],
} as const;

async function openGovernance(page: Page) {
  await page.goto('./#tab=Governance');
  await expect(page.locator('#pipeline figure').first()).toBeVisible();
  await expect(page.locator('[data-print-pending]')).toHaveCount(0);
}

/** Pages and page size of the PDF the browser prints from the current document. */
async function printedPdf(page: Page, path: string) {
  await page.pdf({ path, preferCSSPageSize: true, printBackground: true });
  const pdf = await readFile(path, 'latin1');
  const boxes = [...pdf.matchAll(/\/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)/g)];
  return {
    pages: (pdf.match(/\/Type\s*\/Page[^s]/g) ?? []).length,
    size: boxes.length ? [Number(boxes[0][3]), Number(boxes[0][4])] : [],
  };
}

/** Save the preview as `format` and read the file back. */
async function download(page: Page, format: 'PDF' | 'PNG' | 'JPG') {
  await preview(page).getByRole('radio', { name: format, exact: true }).click();
  const [file] = await Promise.all([
    page.waitForEvent('download'),
    preview(page)
      .getByRole('button', { name: `Download ${format}` })
      .click(),
  ]);
  return { name: file.suggestedFilename(), bytes: await readFile(await file.path()) };
}

/** Page count and first page size of a PDF the dashboard wrote itself. */
function pdfPages(bytes: Buffer) {
  const text = bytes.toString('latin1');
  const box = /\/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]/.exec(text);
  return {
    pages: (text.match(/\/Type \/Page /g) ?? []).length,
    size: box ? [Number(box[1]), Number(box[2])] : [],
  };
}

/** Width and height from a PNG's IHDR, or a JPEG's start-of-frame. */
function pixels(bytes: Buffer) {
  if (bytes.readUInt32BE(0) === 0x89504e47) return [bytes.readUInt32BE(16), bytes.readUInt32BE(20)];
  for (let at = 2; at < bytes.length; at += 2 + bytes.readUInt16BE(at + 2)) {
    if (bytes[at + 1] >= 0xc0 && bytes[at + 1] <= 0xc2)
      return [bytes.readUInt16BE(at + 7), bytes.readUInt16BE(at + 5)];
  }
  return [];
}

test('Print chart previews the selected chart with its filters, legend and data labels', async ({
  page,
  browserErrors,
}) => {
  await openGovernance(page);
  const figure = page.getByRole('figure', { name: `${CHART} — By year` });
  await figure.getByRole('radio', { name: 'Line', exact: true }).click();
  await figure.getByRole('button', { name: 'Triage', exact: true }).click();
  await printButton(page).click();

  await expect(preview(page)).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-print-scope', 'chart');
  await expect(sheet(page).getByRole('heading', { name: CHART })).toBeVisible();
  await expect(sheet(page).locator('[data-print-filter]')).toHaveText([
    'View By year',
    'Chart style Line',
    'Line stacking Cumulative',
    'Scale Counts',
    'Date range 2021 – 2026 · 6 buckets',
    'Hidden series Triage',
  ]);
  // The legend lists the three series drawn; the chart keeps the dashboard's line style.
  await expect(
    sheet(page).locator('[data-print-legend] > button').locator('visible=true'),
  ).toHaveText(['General contributors', 'Committers', 'Maintainers']);
  await expect(sheet(page).locator('.recharts-line')).toHaveCount(3);
  // Six yearly points on the cumulative top line, each labelled with its value.
  await expect(sheet(page).locator('.recharts-label-list text')).toHaveCount(6);
  // Paper has no controls: the sheet shows no switch, button or input.
  await expect(
    sheet(page).locator('[role="radiogroup"], input').locator('visible=true'),
  ).toHaveCount(0);
  await expect(
    sheet(page).locator('button:not([data-print-keep])').locator('visible=true'),
  ).toHaveCount(0);
  await expect(preview(page).getByText(/one page/)).toBeVisible();
  expect(browserErrors).toEqual([]);
});

test('the printed document is the sheet alone, on the chosen paper and orientation', async ({
  page,
  browserName,
}, testInfo) => {
  await openGovernance(page);
  await printButton(page).click();
  await expect(preview(page)).toBeVisible();
  await expect(sheet(page).locator('.recharts-bar-rectangle').first()).toBeVisible();

  await page.emulateMedia({ media: 'print' });
  await expect(page.locator('#root')).toBeHidden();
  await expect(sheet(page)).toBeVisible();
  await expect(preview(page).getByRole('button', { name: 'Print', exact: true })).toBeHidden();
  await expect(preview(page).getByRole('radiogroup', { name: 'Paper size' })).toBeHidden();
  // The tab's own print mode stays off: nothing on the dashboard re-renders for paper.
  await expect(page.locator('html')).not.toHaveAttribute('data-printing', 'true');
  // Nothing reaches past the sheet's edges.
  const overflow = await sheet(page).evaluate((element) => {
    const bounds = element.getBoundingClientRect();
    return [...element.querySelectorAll('*')].filter((child) => {
      const box = child.getBoundingClientRect();
      return box.width > 0 && (box.left < bounds.left - 1 || box.right > bounds.right + 1);
    }).length;
  });
  expect(overflow).toBe(0);
  // Back to the default: page.pdf() prints with screen styles once screen is emulated.
  await page.emulateMedia({ media: null });

  if (browserName !== 'chromium') return;
  for (const [paper, orientation] of [
    ['A4', 'Landscape'],
    ['A4', 'Portrait'],
    ['Letter', 'Landscape'],
    ['Letter', 'Portrait'],
  ] as const) {
    await preview(page).getByRole('radio', { name: paper, exact: true }).click();
    await preview(page).getByRole('radio', { name: orientation, exact: true }).click();
    const name = `${paper} ${orientation.toLowerCase()}` as keyof typeof PAPER_PT;
    await expect(preview(page).getByText(`on ${name} paper, one page`)).toBeVisible();
    const path = testInfo.outputPath(`chart-${paper}-${orientation}.pdf`);
    const printed = await printedPdf(page, path);
    expect(printed.pages).toBe(1);
    expect(printed.size[0]).toBeCloseTo(PAPER_PT[name][0], 0);
    expect(printed.size[1]).toBeCloseTo(PAPER_PT[name][1], 0);
    await testInfo.attach(`chart-${paper}-${orientation}.pdf`, {
      path,
      contentType: 'application/pdf',
    });
  }
});

test('a long ranking prints portrait and states when it needs more than one page', async ({
  page,
  browserName,
}, testInfo) => {
  const ranking: CategoriesDocument = {
    ...PIPELINE_DOCS['hiero-ledger/charts/pipeline_next.json'],
    id: 'ranking',
    kind: 'categories',
    orientation: 'horizontal',
    rank: true,
    top_n: 10,
    dimensions: ['repo', 'series'],
    category: { key: 'repo', label: 'Repository' },
    group: null,
    window: { kind: 'trailing', days: 365, end: '2026-07-25T10:00:00+00:00' },
    rows: Array.from({ length: 120 }, (_, index) => ({
      repo: `hiero-repository-${String(index + 1).padStart(3, '0')}`,
      general_user: 200 - index,
      triage: 3,
      committer: 5,
      maintainer: 2,
    })),
  };
  await page.route('**/charts/pipeline_next.json', (route) => route.fulfill({ json: ranking }));
  await openGovernance(page);
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  const figure = page.getByRole('figure', { name: `${NEXT_CHART} — By month` });
  await figure.getByRole('button', { name: 'Show all 120 repositories' }).click();
  await printButton(page, NEXT_CHART).click();

  await expect(preview(page)).toBeVisible();
  await expect(preview(page).getByText('Best fit is portrait')).toBeVisible();
  await expect(sheet(page).locator('[data-print-filter]')).toHaveText([
    'Scale Counts',
    'Date range 2025-07-25 – 2026-07-25 (365 days)',
    'Showing all 120 repositories',
  ]);
  // Every selected row is drawn, and labelled, rather than clipped to the page.
  await expect(sheet(page).locator('.recharts-yAxis .recharts-cartesian-axis-tick')).toHaveCount(
    120,
  );
  await expect(preview(page).getByRole('status')).toHaveText(/needs 2 pages/);
  if (browserName === 'chromium') {
    const printed = await printedPdf(page, testInfo.outputPath('ranking.pdf'));
    expect(printed.pages).toBe(2);
  }
  // The downloaded PDF breaks the same sheet into the same pages.
  expect(pdfPages((await download(page, 'PDF')).bytes).pages).toBe(2);
});

test('with no data selected, Print chart explains why instead of opening a preview', async ({
  page,
}) => {
  const yearly = PIPELINE_DOCS['hiero-ledger/charts/pipeline_yearly.json'];
  await page.route('**/charts/pipeline_yearly.json', (route) =>
    route.fulfill({
      json: { ...yearly, rows: [], window: { kind: 'calendar', first: null, last: null } },
    }),
  );
  await page.addInitScript(() => {
    window.print = () => {
      (window as unknown as { printed: boolean }).printed = true;
    };
  });
  await openGovernance(page);
  await printButton(page).click();
  const notice = page.getByRole('alert').filter({ hasText: 'Nothing to print for this selection' });
  await expect(notice).toBeVisible();
  await expect(notice).toContainText('No data is available for this selection.');
  await expect(preview(page)).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { printed?: boolean }).printed)).toBe(
    undefined,
  );
  await notice.getByRole('button', { name: 'Dismiss' }).click();
  await expect(notice).toHaveCount(0);
});

test('the preview is paper in dark mode, and closing it restores tab printing', async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await openGovernance(page);
  await printButton(page).click();
  await expect(preview(page)).toBeVisible();
  await expect(sheet(page)).toHaveCSS('background-color', 'rgb(255, 255, 255)');
  await expect(sheet(page)).toHaveCSS('color', 'rgb(27, 27, 27)');
  // The light palette's maintainer blue, though the dashboard around it is dark.
  const fills = await sheet(page)
    .locator('.recharts-bar-rectangle path')
    .evaluateAll((paths) => [...new Set(paths.map((path) => getComputedStyle(path).fill))]);
  expect(fills).toContain('rgb(57, 117, 220)');

  await page.keyboard.press('Escape');
  await expect(preview(page)).toHaveCount(0);
  await expect(printButton(page)).toBeFocused();
  await expect(page.locator('html')).not.toHaveAttribute('data-print-scope', 'chart');
  await page.emulateMedia({ media: 'print' });
  await expect(page.locator('#root')).toBeVisible();
  await expect(page.locator('#roles')).toBeVisible();
  await expect(sheet(page)).toHaveCount(0);
});

test('Download saves the page as PDF, PNG or JPG without the print dialog', async ({ page }) => {
  await page.addInitScript(() => {
    window.print = () => {
      (window as unknown as { printed: boolean }).printed = true;
    };
  });
  await openGovernance(page);
  await printButton(page).click();
  await preview(page).getByRole('radio', { name: 'A4', exact: true }).click();
  await preview(page).getByRole('radio', { name: 'Landscape', exact: true }).click();
  await expect(sheet(page).locator('.recharts-bar-rectangle').first()).toBeVisible();

  const pdf = await download(page, 'PDF');
  expect(pdf.name).toBe('unique-active-contributors-by-role-a4-landscape.pdf');
  expect(pdf.bytes.subarray(0, 5).toString()).toBe('%PDF-');
  const printed = pdfPages(pdf.bytes);
  expect(printed.pages).toBe(1);
  expect(printed.size[0]).toBeCloseTo(841.89, 1);
  expect(printed.size[1]).toBeCloseTo(595.28, 1);

  // A4 landscape at 288 dots per inch.
  const png = await download(page, 'PNG');
  expect(png.name).toBe('unique-active-contributors-by-role-a4-landscape.png');
  expect(pixels(png.bytes)).toEqual([3368, 2381]);
  const jpg = await download(page, 'JPG');
  expect(jpg.name).toBe('unique-active-contributors-by-role-a4-landscape.jpg');
  expect(pixels(jpg.bytes)).toEqual([3368, 2381]);

  expect(await page.evaluate(() => (window as unknown as { printed?: boolean }).printed)).toBe(
    undefined,
  );
  await expect(preview(page)).toBeVisible();
});
