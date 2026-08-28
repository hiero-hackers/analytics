/**
 * Serves the `fixtures.ts` API tree to the unit suite through a `fetch` stub
 * keyed by URL suffix — the same contract the real API honours.
 *
 * This lives apart from the fixture data because it imports vitest, and the
 * e2e setup loads that data outside the test runner to write it to disk.
 */

import { vi } from 'vitest';
import { ROUTES } from './fixtures';

/**
 * Stub global fetch to serve the fixture API; returns the spy for assertions.
 * `overrides` lets a test intercept specific routes (e.g. to delay or fail a
 * request) while every other route still serves its normal fixture — so a
 * test controlling one request doesn't have to also know every other request
 * the page happens to make.
 */
export function stubApi(overrides: Record<string, () => Response | Promise<Response>> = {}) {
  return vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const key = String(url);
      const override = Object.entries(overrides).find(([suffix]) => key.endsWith(suffix));
      if (override) return override[1]();
      const match = Object.entries(ROUTES).find(([suffix]) => key.endsWith(suffix));
      if (!match) {
        return new Response('not found', { status: 404 });
      }
      return new Response(JSON.stringify(match[1]), { status: 200 });
    }),
  );
}
