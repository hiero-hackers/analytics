import { useState } from 'react';

/** A GitHub login with its avatar; initials stand in when the image fails. */
export function ContributorCell({
  login,
  compact = false,
}: {
  login: string;
  /** A smaller avatar, for dense grids such as a printed heatmap. */
  compact?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  if (!/^[a-zA-Z0-9][a-zA-Z0-9-]{0,38}(\[bot\])?$/.test(login)) return <>{login}</>;
  return (
    <a
      href={`https://github.com/${encodeURIComponent(login)}`}
      target="_blank"
      rel="noopener noreferrer"
      className={`group/person inline-flex items-center ${compact ? 'gap-1.5' : 'gap-2.5'} rounded-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring`}
    >
      <span
        className={`relative flex ${compact ? 'size-5 text-[8px]' : 'size-8 text-xs'} shrink-0 items-center justify-center overflow-hidden rounded-full border bg-muted text-muted-foreground`}
        aria-hidden="true"
      >
        {login.slice(0, 2).toUpperCase()}
        {!failed && (
          <img
            src={`https://avatars.githubusercontent.com/${encodeURIComponent(login)}?s=64`}
            className="absolute inset-0 size-full bg-muted object-cover"
            alt=""
            width={32}
            height={32}
            // A printed grid has no scroll to trigger a lazy load before the page is captured.
            loading={compact ? 'eager' : 'lazy'}
            referrerPolicy="no-referrer"
            onError={() => setFailed(true)}
          />
        )}
      </span>
      <span className="group-hover/person:text-link group-hover/person:underline underline-offset-4">
        {login}
      </span>
    </a>
  );
}
