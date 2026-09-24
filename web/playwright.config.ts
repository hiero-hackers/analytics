/**
 * Smoke-level end-to-end config: Chromium only, against the built app served
 * from a staged directory (see `e2e/build-site.ts`). This layer exists to catch
 * what the vitest suite structurally cannot — the real bundle booting, real
 * `fetch` over base-relative URLs, and the page's own CSP — so it deliberately
 * stays small rather than growing into a browser matrix.
 *
 * The server command builds and stages the site itself, so the site is ready
 * before the first request regardless of how Playwright orders its startup.
 */

import { defineConfig, devices } from '@playwright/test';

const HOST = '127.0.0.1';
const PORT = 4173;
const BASE_URL = `http://${HOST}:${PORT}`;

export default defineConfig({
  testDir: './e2e',
  // A smoke suite that flakes is worse than no smoke suite: it trains people to
  // re-run CI instead of reading it. One worker, no retries — any flake here is
  // a bug to fix rather than to absorb.
  workers: 1,
  retries: 0,
  forbidOnly: Boolean(process.env.CI),
  reporter: process.env.CI ? [['github'], ['list']] : [['list']],
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run e2e:serve',
    url: BASE_URL,
    env: { E2E_PORT: String(PORT) },
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
