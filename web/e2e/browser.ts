import { test as base, expect } from '@playwright/test';

export const test = base.extend<{ browserErrors: string[] }>({
  browserErrors: [
    async ({ page, baseURL }, use) => {
      const errors: string[] = [];
      const uncaught: string[] = [];
      const allowed = new URL(baseURL as string).origin;
      page.on('pageerror', (error) => {
        errors.push(error.message);
        uncaught.push(error.message);
      });
      page.on('console', (message) => {
        if (message.type() === 'error') errors.push(message.text());
      });
      // Use real local fetches, never the live API or remote chart hosts.
      await page.route('**/*', async (route) => {
        const url = new URL(route.request().url());
        if (url.origin === allowed || url.protocol === 'data:' || url.protocol === 'blob:') {
          await route.continue();
        } else {
          errors.push(`Unexpected external request: ${url.href}`);
          await route.abort();
        }
      });
      await use(errors);
      expect(errors.filter((error) => error.startsWith('Unexpected external request:'))).toEqual(
        [],
      );
      expect(uncaught).toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };
