/** The work-in-progress disclaimer footer, and the page's report-a-problem link. */

import { Badge } from '@/components/ui/badge';
import { safeUrl } from '../safety';

export function WipFooter({ issuesUrl }: { issuesUrl?: string }) {
  // Only the affiliations table carries a contextual "Suggest a correction"
  // action, because its data is hand-curated rather than computed. Telling every
  // reader to "use a table's link" therefore sent most of them hunting for
  // something that isn't on their tab; this footer is the general route.
  const href = issuesUrl ? safeUrl(issuesUrl) : null;
  return (
    <footer className="max-w-[62ch] text-xs/relaxed text-muted-foreground">
      <Badge variant="warn" className="mr-1.5 align-middle">
        Work in progress
      </Badge>
      This dashboard is under active development. Organisation affiliations are curated and still
      being verified — figures are directional and may change.{' '}
      {href ? (
        <>
          Spotted something wrong?{' '}
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-link underline-offset-4 hover:underline"
          >
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
