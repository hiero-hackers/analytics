# Browser verification

```sh
npm ci
npx playwright install chromium
npm run test:e2e
```

The suite builds the app, stages `dist` and the typed component-test API
fixtures under `.e2e/site`, then serves them at `/analytics/`. Every browser
request must remain on that local server. No live API, credentials, Python
pipeline, or duplicate JSON fixtures are needed. The print cases derive larger
tables and a slideshow from the shared fixtures to exercise virtualisation,
wrapping, and explicit row limits.

`npm run build` also typechecks these tests and their fixtures. Vitest is scoped
to `src` so the two runners do not collect each other's files. This follows the
shared-fixture staging approach agreed in issue #332; it does not add another
CI workflow.

For a local Firefox compatibility check:

```sh
npx playwright install firefox
npm run test:e2e:firefox
```

Chromium produces a `governance.pdf` in its test-results directory for visual
review of running footers and page boundaries. Firefox supports print-media
checks but Playwright cannot export its native PDF. Fixture chart PNGs are
one-pixel loading placeholders: chart legibility and effective resolution must
also be reviewed with real dashboard images, as described in the print notes.
