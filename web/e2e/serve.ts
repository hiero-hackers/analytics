/**
 * Stages the e2e site and serves it as a plain static host.
 *
 * Deliberately not `vite preview`. Preview inherits `server.proxy` from
 * `vite.config.ts`, which forwards `/data` and `/charts` to the dev data server
 * on :8642 — with that server absent the API answers 502, and the dashboard
 * under test never loads. Preview also falls back to `index.html` for unknown
 * paths, which would turn "the manifest names a file that isn't there" into a
 * JSON parse error instead of the 404 it is.
 *
 * Production is GitHub Pages: a static host that returns the file or 404. That
 * is what this serves, so the suite tests the deployment it actually ships to.
 */

import { createReadStream, existsSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { extname, resolve, sep } from 'node:path';
import { buildSite, SITE_DIR } from './build-site.ts';

const HOST = '127.0.0.1';
/** Set by Playwright's `webServer.env`, so the config owns the port. */
const PORT = Number(process.env.E2E_PORT ?? 4173);

const TYPES: Record<string, string> = {
  '.css': 'text/css; charset=utf-8',
  '.csv': 'text/csv; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
};

await buildSite();

const server = createServer((request, response) => {
  const { pathname } = new URL(request.url ?? '/', `http://${HOST}:${PORT}`);
  const requested = decodeURIComponent(pathname).replace(/^\/+/, '');
  const file = resolve(SITE_DIR, requested === '' ? 'index.html' : requested);

  // Nothing outside the staged site is servable, whatever the path traversal.
  if (file !== SITE_DIR && !file.startsWith(SITE_DIR + sep)) {
    response.writeHead(403).end('forbidden');
    return;
  }
  if (!existsSync(file) || !statSync(file).isFile()) {
    response.writeHead(404).end('not found');
    return;
  }

  response.writeHead(200, { 'content-type': TYPES[extname(file)] ?? 'application/octet-stream' });
  createReadStream(file).pipe(response);
});

server.listen(PORT, HOST, () => {
  console.log(`e2e site serving ${SITE_DIR} on http://${HOST}:${PORT}`);
});
