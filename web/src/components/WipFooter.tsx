/** The work-in-progress disclaimer footer, and the page's report-a-problem link. */

import { safeUrl } from '../safety';

export function WipFooter({ issuesUrl }: { issuesUrl?: string }) {
  // Only the affiliations table carries a contextual "Suggest a correction"
  // action, because its data is hand-curated rather than computed. Telling every
  // reader to "use a table's link" therefore sent most of them hunting for
  // something that isn't on their tab; this footer is the general route.
  const href = issuesUrl ? safeUrl(issuesUrl) : null;
  return (
    <footer className="mb-2 max-w-[62ch] text-[13px] leading-normal text-muted">
      <span className="mr-1.5 inline-block rounded bg-warn/20 px-2 py-[2px] text-[11px] font-semibold tracking-[0.04em] uppercase text-warn-ink">
        Work in progress
      </span>{' '}
      This dashboard is under active development. Organisation affiliations are curated and still
      being verified — figures are directional and may change.{' '}
      {href ? (
        <>
          Spotted something wrong?{' '}
          <a href={href} target="_blank" rel="noopener noreferrer" className="cell-link">
            Open an issue
          </a>
          . Affiliations can also be corrected from that table&rsquo;s own &ldquo;Suggest a
          correction&rdquo; link.
        </>
      ) : (
        <>Spotted something wrong? Please raise it with the maintainers.</>
      )}
    </footer>
  );
}
