import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  workers: 2,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:4173/analytics/',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  // The normal smoke/print command runs Chromium. Firefox is an explicit
  // local compatibility check, not a second CI pipeline or PDF generator.
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
  ],
  webServer: {
    command:
      'npm run build -- --base=/analytics/ && node --experimental-strip-types e2e/prepare.ts && npm run preview -- --host 127.0.0.1 --port 4173 --strictPort --base=/analytics/ --outDir=.e2e/site',
    url: 'http://127.0.0.1:4173/analytics/',
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
