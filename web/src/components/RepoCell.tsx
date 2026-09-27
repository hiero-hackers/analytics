/**
 * A repository name as GitHub shows it: the owner muted, the name in weight,
 * linking to the repository. Bare names ("hiero-sdk-js") resolve against the
 * organisation the dashboard is showing; anything that does not look like a
 * repository name renders as plain text.
 */

import { useContext } from 'react';
import { OrgContext } from '../orgContext';

const NAME = /^[A-Za-z0-9_.-]+$/;

export function RepoCell({ name }: { name: string }) {
  const org = useContext(OrgContext);
  const [owner, repo] = name.includes('/') ? name.split('/', 2) : [null, name];
  if (!NAME.test(repo) || (owner !== null && !NAME.test(owner))) return <>{name}</>;
  const home = owner ?? org;
  const label = (
    <>
      {owner && <span className="font-normal text-muted-foreground">{owner}/</span>}
      {repo}
    </>
  );
  if (!home) return <span className="font-medium">{label}</span>;
  return (
    <a
      href={`https://github.com/${encodeURIComponent(home)}/${encodeURIComponent(repo)}`}
      target="_blank"
      rel="noopener noreferrer"
      className="rounded-sm font-medium outline-none underline-offset-4 hover:text-link hover:underline focus-visible:ring-2 focus-visible:ring-ring"
    >
      {label}
    </a>
  );
}
